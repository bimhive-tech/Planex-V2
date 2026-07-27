"""AI assistant tests. The OpenAI client is always mocked here — never call
the real API in automated tests (cost + nondeterminism)."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.accounts.constants import COMPANY_ADMIN_PERMISSIONS, Permission, SeededRole
from apps.accounts.models import Company, Membership, Role, User
from apps.projects.models import Project, ProjectScope

from .models import AiFeatureRequest, ChatMessage, ChatSession
from .services import stream_agent_reply
from .tools import (
    commit_proposal,
    flag_unsupported_category,
    list_projects,
    propose_create_project,
    propose_import_tree,
)

STRONG_PW = "Str0ngPassw0rd!"


def _fake_chunk(content=None, tool_calls=None, finish_reason=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)])


def _fake_tool_call_delta(index, call_id=None, name=None, arguments=None):
    fn = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=call_id, function=fn)


class AiAssistantAccessTests(TestCase):
    """Both gates (company.ai_enabled + USE_AI_ASSISTANT) must hold."""

    def setUp(self):
        self.company = Company.objects.create(name="Acme")
        self.client = APIClient()

    def _user_with(self, permissions, ai_enabled):
        self.company.ai_enabled = ai_enabled
        self.company.save(update_fields=["ai_enabled"])
        role = Role.objects.create(company=self.company, name="R", permissions=permissions)
        user = User.objects.create_user(email=f"u{ai_enabled}{len(permissions)}@acme.com",
                                         password=STRONG_PW, company=self.company)
        Membership.objects.create(company=self.company, user=user, role=role)
        return user

    def test_company_ai_disabled_blocks_even_with_permission(self):
        user = self._user_with([Permission.USE_AI_ASSISTANT.value], ai_enabled=False)
        self.client.force_authenticate(user)
        res = self.client.get("/api/ai/sessions/")
        self.assertEqual(res.status_code, 403)

    def test_missing_permission_blocks_even_with_company_enabled(self):
        user = self._user_with([Permission.VIEW_PROJECTS.value], ai_enabled=True)
        self.client.force_authenticate(user)
        res = self.client.get("/api/ai/sessions/")
        self.assertEqual(res.status_code, 403)

    def test_both_gates_open_allows_access(self):
        user = self._user_with([Permission.USE_AI_ASSISTANT.value], ai_enabled=True)
        self.client.force_authenticate(user)
        res = self.client.get("/api/ai/sessions/")
        self.assertEqual(res.status_code, 200)


class ToolsTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme", ai_enabled=True)
        role = Role.objects.create(company=self.company, name=SeededRole.COMPANY_ADMIN,
                                    permissions=COMPANY_ADMIN_PERMISSIONS)
        self.user = User.objects.create_user(email="u@acme.com", password=STRONG_PW, company=self.company)
        Membership.objects.create(company=self.company, user=self.user, role=role)

        self.other_company = Company.objects.create(name="Other")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL)
        self.other_project = Project.objects.create(
            company=self.other_company, name="Secret", project_type=Project.ProjectType.COMMERCIAL)

    def test_list_projects_is_company_scoped(self):
        result = list_projects(self.user)
        names = {p["name"] for p in result["projects"]}
        self.assertEqual(names, {"Tower"})  # not "Secret", a different company

    def test_list_projects_requires_permission(self):
        no_perm_role = Role.objects.create(company=self.company, name="None", permissions=[])
        Membership.objects.filter(user=self.user).delete()
        Membership.objects.create(company=self.company, user=self.user, role=no_perm_role)
        with self.assertRaises(PermissionDenied):
            list_projects(self.user)

    def test_propose_create_project_does_not_create_until_confirmed(self):
        before = Project.objects.count()
        proposal = propose_create_project(self.user, name="New Tower", project_type="commercial")
        self.assertTrue(proposal["valid"])
        self.assertEqual(Project.objects.count(), before)  # nothing written yet

        result = commit_proposal(self.user, proposal)
        self.assertEqual(Project.objects.count(), before + 1)
        self.assertEqual(Project.objects.get(pk=result["id"]).name, "New Tower")

    def test_propose_import_tree_does_not_write_until_confirmed(self):
        tree = [{
            "name": "Stage A", "scope_type": "stage",
            "children": [{
                "name": "Zone A", "scope_type": "zone",
                "activities": [{"name": "Task 1", "progress_percent": 50, "weight": 1}],
            }],
        }]
        proposal = propose_import_tree(self.user, project_id=str(self.project.id), tree=tree)
        self.assertTrue(proposal["valid"])
        self.assertEqual(proposal["counts"], {"scopes": 2, "activities": 1, "milestones": 0})
        self.assertEqual(ProjectScope.objects.filter(project=self.project).count(), 0)  # not written yet

        commit_proposal(self.user, proposal)
        self.assertEqual(ProjectScope.objects.filter(project=self.project).count(), 2)
        zone = ProjectScope.objects.get(project=self.project, name="Zone A")
        self.assertEqual(zone.activities.get().name, "Task 1")

    def test_propose_import_tree_rejects_a_project_in_another_company(self):
        tree = [{"name": "Stage A", "scope_type": "stage"}]
        with self.assertRaises(PermissionDenied):
            propose_import_tree(self.user, project_id=str(self.other_project.id), tree=tree)

    def test_flag_unsupported_category_logs_a_pending_request(self):
        result = flag_unsupported_category(self.user, summary="Safety incident log column", project_id=str(self.project.id))
        req = AiFeatureRequest.objects.get(pk=result["id"])
        self.assertEqual(req.status, AiFeatureRequest.Status.PENDING)
        self.assertEqual(req.company, self.company)


class AgentLoopTests(TestCase):
    """The agent loop itself, against a mocked OpenAI client."""

    def setUp(self):
        self.company = Company.objects.create(name="Acme", ai_enabled=True)
        role = Role.objects.create(company=self.company, name=SeededRole.COMPANY_ADMIN,
                                    permissions=COMPANY_ADMIN_PERMISSIONS)
        self.user = User.objects.create_user(email="u@acme.com", password=STRONG_PW, company=self.company)
        Membership.objects.create(company=self.company, user=self.user, role=role)
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL)
        self.session = ChatSession.objects.create(company=self.company, user=self.user)
        ChatMessage.objects.create(session=self.session, role=ChatMessage.Role.USER,
                                    content="How many projects do we have?")

    def _events(self, chunks_per_call):
        """chunks_per_call: list of lists of fake chunks, one inner list per model call."""
        calls = iter(chunks_per_call)

        def fake_create(**kwargs):
            return next(calls)

        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
        with patch("apps.ai_assistant.services.get_client", return_value=fake_client), \
             patch("apps.ai_assistant.services.get_model", return_value="gpt-4o"):
            return [json.loads(line[len("data: "):]) for line in
                    "".join(stream_agent_reply(self.session, self.user)).splitlines() if line.startswith("data: ")]

    def test_plain_text_reply_saves_one_assistant_message(self):
        events = self._events([[
            _fake_chunk(content="You have "),
            _fake_chunk(content="1 project."),
            _fake_chunk(finish_reason="stop"),
        ]])
        self.assertEqual([e["type"] for e in events], ["delta", "delta", "done"])
        assistant_msgs = self.session.messages.filter(role=ChatMessage.Role.ASSISTANT)
        self.assertEqual(assistant_msgs.count(), 1)
        self.assertEqual(assistant_msgs.get().content, "You have 1 project.")

    def test_tool_call_then_final_reply(self):
        tool_call = _fake_tool_call_delta(0, call_id="call_1", name="list_projects", arguments="{}")
        events = self._events([
            [_fake_chunk(tool_calls=[tool_call]), _fake_chunk(finish_reason="tool_calls")],
            [_fake_chunk(content="You have 1 project: Tower."), _fake_chunk(finish_reason="stop")],
        ])
        self.assertEqual(events[-1]["type"], "done")
        tool_msgs = self.session.messages.filter(role=ChatMessage.Role.TOOL)
        self.assertEqual(tool_msgs.count(), 1)
        result = json.loads(tool_msgs.get().content)
        self.assertEqual(result["projects"][0]["name"], "Tower")
        # No proposal event for a read tool.
        self.assertNotIn("proposal", [e["type"] for e in events])

    def test_propose_tool_result_is_compacted_before_replay_but_full_in_db(self):
        """A propose_import_tree result can carry an entire schedule tree. The
        model already generated that tree once (in its own tool_calls
        arguments); echoing it back in full as the tool result would double
        an already-large payload on every future round. The DB keeps the full
        result (the confirm endpoint needs it) — only what's replayed to the
        model gets trimmed."""
        big_tree = [{"name": "Stage", "scope_type": "stage",
                     "activities": [{"name": f"Task {i}", "progress_percent": 0, "weight": 1} for i in range(50)]}]
        args = json.dumps({"project_id": str(self.project.id), "tree": big_tree})
        tool_call = _fake_tool_call_delta(0, call_id="call_1", name="propose_import_tree", arguments=args)

        captured_messages = []

        def fake_create(**kwargs):
            captured_messages.append(kwargs["messages"])
            return next(calls)

        calls = iter([
            [_fake_chunk(tool_calls=[tool_call]), _fake_chunk(finish_reason="tool_calls")],
            [_fake_chunk(content="Want me to import this?"), _fake_chunk(finish_reason="stop")],
        ])
        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
        with patch("apps.ai_assistant.services.get_client", return_value=fake_client), \
             patch("apps.ai_assistant.services.get_model", return_value="gpt-4o"):
            list("".join(stream_agent_reply(self.session, self.user)))

        # Second call's replayed tool message must not carry the tree.
        second_call_tool_msg = next(m for m in captured_messages[1] if m.get("role") == "tool")
        replayed = json.loads(second_call_tool_msg["content"])
        self.assertNotIn("tree", replayed)
        self.assertTrue(replayed["valid"])

        # But the persisted DB row still has it in full (confirm needs it).
        db_tool_msg = self.session.messages.get(tool_name="propose_import_tree")
        stored = json.loads(db_tool_msg.content)
        self.assertEqual(len(stored["tree"][0]["activities"]), 50)

    def test_missing_api_key_yields_a_clean_error_event(self):
        from .openai_client import AiNotConfigured

        with patch("apps.ai_assistant.services.get_client", side_effect=AiNotConfigured("OPENAI_API_KEY is not set.")):
            events = [json.loads(line[len("data: "):]) for line in
                      "".join(stream_agent_reply(self.session, self.user)).splitlines() if line.startswith("data: ")]
        self.assertEqual(events, [{"type": "error", "message": "OPENAI_API_KEY is not set."}])

    def test_propose_tool_call_yields_a_proposal_event_without_writing(self):
        args = json.dumps({"name": "New Tower", "project_type": "commercial"})
        tool_call = _fake_tool_call_delta(0, call_id="call_1", name="propose_create_project", arguments=args)
        events = self._events([
            [_fake_chunk(tool_calls=[tool_call]), _fake_chunk(finish_reason="tool_calls")],
            [_fake_chunk(content="Want me to create it?"), _fake_chunk(finish_reason="stop")],
        ])
        proposals = [e for e in events if e["type"] == "proposal"]
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["proposal"]["action"], "create_project")
        self.assertEqual(Project.objects.filter(name="New Tower").count(), 0)  # not committed
