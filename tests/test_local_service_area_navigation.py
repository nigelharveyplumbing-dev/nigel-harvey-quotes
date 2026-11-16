"""Public local-page links should stay focused without losing discoverability."""

from bs4 import BeautifulSoup

from business.public_pages import (
    LOCAL_SERVICE_AREA_NAMES,
    LOCAL_SERVICE_NEARBY_AREAS,
    LOCAL_SERVICE_PAGES,
    LOCATION_PAGES,
    render_local_service_location_page,
)


def _url(path, request=None):
    return "https://www.nigelharveyplumbing.co.uk" + path


def test_nearby_map_covers_exactly_the_published_service_towns():
    service_towns = {p["slug"] for p in LOCATION_PAGES if p["slug"] != "farnborough"}
    assert set(LOCAL_SERVICE_NEARBY_AREAS) == service_towns
    assert service_towns.issubset(LOCAL_SERVICE_AREA_NAMES)
    for town, neighbours in LOCAL_SERVICE_NEARBY_AREAS.items():
        assert 3 <= len(neighbours) <= 4
        assert len(neighbours) == len(set(neighbours))
        assert town not in neighbours
        assert set(neighbours) <= service_towns


def test_all_local_service_pages_keep_relevant_crawlable_area_links():
    for service in LOCAL_SERVICE_PAGES:
        for location in LOCATION_PAGES:
            if location["slug"] == "farnborough":
                continue
            html = render_local_service_location_page(
                service, location, "", absolute_url=_url,
            )
            soup = BeautifulSoup(html, "html.parser")
            heading = soup.find("h2", string="Other Local Service Areas")
            assert heading, (service["slug"], location["slug"])
            urls = [a["href"] for a in heading.find_next("div", class_="pill-links").find_all("a")]
            expected = [
                f'/{service["slug"]}-{neighbour}'
                for neighbour in LOCAL_SERVICE_NEARBY_AREAS[location["slug"]]
            ]
            assert urls == expected
            assert all(url.startswith("/") and not url.startswith("//") for url in urls)
            assert soup.select_one('link[rel="canonical"]')
