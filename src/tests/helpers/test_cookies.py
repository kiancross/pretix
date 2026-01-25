import pytest

from pretix.helpers.cookies import can_send_partitioned_cookie

CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
SAFARI_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
SAFARI_IOS_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
FIREFOX_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"


@pytest.mark.parametrize("useragent,expected", [
    (CHROME_UA, True),
    (FIREFOX_UA, True),
    (SAFARI_UA, False),
    (SAFARI_IOS_UA, False),
    ("", True),
])
def test_can_send_partitioned_cookie(useragent, expected):
    assert can_send_partitioned_cookie(useragent) == expected
