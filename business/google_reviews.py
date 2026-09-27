"""Live Google review retrieval and HTML rendering for the public homepage."""

import requests
from html import escape
from urllib.parse import quote_plus

def google_reviews_html(*, GOOGLE_PLACES_API_KEY, GOOGLE_REVIEWS_URL, _google_place_id):
    """Build the live Google rating/review section. Falls back cleanly if Google is unavailable."""
    fallback = (
        '<div class="stars">★★★★★</div>'
        '<h2>Customer reviews</h2>'
        '<p class="muted">See feedback from customers on Google, or leave a review after Nigel has completed your plumbing work.</p>'
        f'<a class="btn" href="{escape(GOOGLE_REVIEWS_URL, quote=True)}" target="_blank" rel="noopener">Read Google Reviews</a>'
    )
    if not GOOGLE_PLACES_API_KEY:
        print("Google reviews fallback: GOOGLE_PLACES_API_KEY is not set", flush=True)
        return fallback
    place_id = _google_place_id()
    if not place_id:
        print("Google reviews fallback: no Google Place ID could be resolved", flush=True)
        return fallback
    try:
        print(f"Google reviews: requesting Place Details for place ID ending ...{place_id[-8:]}", flush=True)
        response = requests.get(
            f"https://places.googleapis.com/v1/places/{quote_plus(place_id)}",
            headers={
                "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
                "X-Goog-FieldMask": "displayName,rating,userRatingCount,reviews,googleMapsLinks.reviewsUri",
            },
            params={"languageCode": "en", "regionCode": "GB"},
            timeout=8,
        )
        if not response.ok:
            print(f"Google reviews HTTP {response.status_code}: {response.text[:1500]}", flush=True)
            response.raise_for_status()
        data = response.json()
        rating = data.get("rating")
        count = data.get("userRatingCount")
        reviews = data.get("reviews") or []
        reviews_url = ((data.get("googleMapsLinks") or {}).get("reviewsUri") or GOOGLE_REVIEWS_URL).strip()
        print(f"Google reviews response: rating={rating!r}, userRatingCount={count!r}, reviews={len(reviews)}", flush=True)
        if rating is None and not reviews:
            print(f"Google reviews fallback: response contained no rating/reviews. Keys: {list(data.keys())}", flush=True)
            return fallback

        rating_text = f"{float(rating):.1f}" if rating is not None else ""
        count_text = f"{int(count):,} Google review" + ("" if int(count) == 1 else "s") if count is not None else "Google reviews"
        cards = []
        for review in reviews[:3]:
            author = review.get("authorAttribution") or {}
            author_name = escape(author.get("displayName") or "Google customer")
            author_uri = escape(author.get("uri") or review.get("googleMapsUri") or reviews_url, quote=True)
            photo_uri = escape(author.get("photoUri") or "", quote=True)
            review_uri = escape(review.get("googleMapsUri") or reviews_url, quote=True)
            review_text = escape(((review.get("text") or {}).get("text") or "").strip())
            relative_time = escape(review.get("relativePublishTimeDescription") or "")
            stars = max(0, min(5, int(round(float(review.get("rating") or 0)))))
            avatar = (f'<a href="{author_uri}" target="_blank" rel="noopener"><img class="review-avatar" src="{photo_uri}" alt="{author_name}"></a>' if photo_uri else '<div class="review-avatar review-avatar-fallback">G</div>')
            body = f'<p class="review-text">{review_text}</p>' if review_text else ""
            cards.append(
                '<article class="google-review-card">'
                f'<div class="review-author">{avatar}<div><a href="{author_uri}" target="_blank" rel="noopener"><strong>{author_name}</strong></a><div class="review-meta"><span class="mini-stars">{"★" * stars}{"☆" * (5-stars)}</span> {relative_time}</div></div></div>'
                f'{body}<a class="review-source" href="{review_uri}" target="_blank" rel="noopener">View on Google</a>'
                '</article>'
            )

        cards_html = '<div class="google-review-grid">' + ''.join(cards) + '</div>' if cards else ''
        summary = f'<div class="google-rating"><strong>{rating_text}</strong><span class="stars">★★★★★</span><span>{escape(count_text)}</span></div>' if rating_text else ''
        return (
            '<div class="google-brand"><img src="https://www.gstatic.com/images/branding/googlelogo/1x/googlelogo_color_74x24dp.png" alt="Google"></div>'
            '<h2>Customer reviews</h2>'
            f'{summary}{cards_html}'
            "<p class=\"review-note\">Reviews supplied by Google and shown in Google’s relevance order.</p>"
            f'<a class="btn" href="{escape(reviews_url, quote=True)}" target="_blank" rel="noopener">Read all Google Reviews</a>'
        )
    except Exception as exc:
        print(f"Google Places reviews failed: {type(exc).__name__}: {exc}", flush=True)
        return fallback
