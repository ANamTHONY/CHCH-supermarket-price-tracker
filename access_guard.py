"""Recognize explicit denial pages without retrying or bypassing them."""


class AccessDeniedError(RuntimeError):
    pass


def is_denied(title, body):
    title = (title or '').strip().lower()
    body = (body or '').strip().lower()
    return title == 'access denied' or (
        body.startswith('access denied') and
        ("permission to access" in body or 'errors.edgesuite.net' in body)
    )


def check_access(driver):
    text = driver.execute_script('return document.body ? document.body.innerText.slice(0,2000) : "";')
    if is_denied(driver.title, text):
        raise AccessDeniedError('Website denied access; no further requests for this brand in this run')
