"""Shared pagination. Page-number style for moderate admin lists (users, roles,
companies) — gives total counts for the 'showing X of Y' footer. Large
append-heavy tables (reports/activity) will use cursor pagination instead."""
from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100
