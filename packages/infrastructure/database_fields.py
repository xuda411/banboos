"""Legacy field names copied as a small adapter contract, not a DB dependency."""
PRICE_FIELDS = tuple(
    f"p{total_minutes // 60:02d}{total_minutes % 60:02d}"
    for total_minutes in range(15, 24 * 60 + 1, 15)
)
