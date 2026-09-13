import httpx
import pytest

from app.services.research import scraper


@pytest.fixture
def install_transport(monkeypatch):
    original = httpx.AsyncClient
    # Deterministic DNS policy: exercise the shared validator without live DNS.
    monkeypatch.setattr('socket.getaddrinfo', lambda host, port: [(2, 1, 6, '', (host if host == '127.0.0.1' else '93.184.216.34', 443))])

    def install(handler):
        monkeypatch.setattr(scraper.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    return install


@pytest.mark.asyncio
async def test_fetch_failure_never_fabricates_evidence(install_transport):
    install_transport(lambda request: httpx.Response(503))
    result = await scraper.web_scraper.scrape_url('https://example.com/report')
    assert result['is_scraped'] is False
    for key in ('authors', 'published_date', 'extracted_text', 'content_hash'):
        assert result[key] == ''


@pytest.mark.asyncio
async def test_private_redirect_is_blocked_before_fetch(install_transport):
    visited = []
    def handler(request):
        visited.append(str(request.url))
        return httpx.Response(302, headers={'location': 'http://127.0.0.1/private'})
    install_transport(handler)
    result = await scraper.web_scraper.scrape_url('https://example.com/report')
    assert result['is_scraped'] is False
    assert visited == ['https://example.com/report']


@pytest.mark.asyncio
async def test_real_text_preserved_missing_metadata_not_invented(install_transport):
    body = '<title>Real report</title><p>This is actual evidence contained in the downloaded document.</p>'
    install_transport(lambda request: httpx.Response(200, text=body))
    result = await scraper.web_scraper.scrape_url('https://example.com/report')
    assert result['is_scraped'] is True
    assert result['title'] == 'Real report'
    assert result['authors'] == result['published_date'] == ''
    assert result['extracted_text'] == 'This is actual evidence contained in the downloaded document.'


@pytest.mark.asyncio
async def test_redirect_limit_and_response_limit(install_transport, monkeypatch):
    visited = []
    def redirect(request):
        visited.append(str(request.url))
        return httpx.Response(302, headers={'location': '/again'})
    install_transport(redirect)
    assert (await scraper.web_scraper.scrape_url('https://example.com/report'))['is_scraped'] is False
    assert len(visited) <= 5
    monkeypatch.setattr(scraper.WebScraper, 'MAX_RESPONSE_BYTES', 32)
    install_transport(lambda request: httpx.Response(200, content=b'x' * 33))
    result = await scraper.web_scraper.scrape_url('https://example.com/report')
    assert result['is_scraped'] is False
    assert result['extracted_text'] == ''


@pytest.mark.asyncio
async def test_relative_redirect_and_actual_metadata(install_transport):
    def handler(request):
        if request.url.path == '/report':
            return httpx.Response(302, headers={'location': '/final'})
        return httpx.Response(200, text='<meta name="author" content="Actual Author"><meta property="article:published_time" content="2026-09-01"><p>This paragraph is actual evidence from the final response.</p>')
    install_transport(handler)
    result = await scraper.web_scraper.scrape_url('https://example.com/report')
    assert result['is_scraped'] is True
    assert result['authors'] == 'Actual Author'
    assert result['published_date'] == '2026-09-01'


@pytest.mark.asyncio
async def test_private_initial_url_never_contacts_server(install_transport):
    visited = []
    def handler(request):
        visited.append(str(request.url))
        return httpx.Response(200, text='must not be read')
    install_transport(handler)
    result = await scraper.web_scraper.scrape_url('http://127.0.0.1/private')
    assert result['is_scraped'] is False
    assert visited == []
