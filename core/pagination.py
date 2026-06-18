from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Default pagination with an opt-in, bounded `page_size` override.

    Used by listing endpoints (e.g. the QR-code gallery) that need to pull a large
    batch in one request: `?page_size=500`. Capped to protect the server.
    """

    page_size_query_param = 'page_size'
    max_page_size = 1000
