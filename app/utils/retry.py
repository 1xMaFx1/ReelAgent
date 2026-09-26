import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def transient(error: BaseException) -> bool:
    return isinstance(error, httpx.TransportError) or (
        isinstance(error, httpx.HTTPStatusError)
        and (error.response.status_code == 429 or error.response.status_code >= 500)
    )


network_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=8),
    retry=retry_if_exception(transient),
    reraise=True,
)


@network_retry
async def request(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
    response = await client.request(method, url, **kwargs)
    response.raise_for_status()
    return response
