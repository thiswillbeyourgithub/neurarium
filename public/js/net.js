// The one fetch + status check. Each caller keeps its own error wording (it lands
// in a banner, a console line or a retry), so the message is a parameter.

const httpStatus = (res) => `HTTP ${res.status}`;

/**
 * Fetch `url` and throw on a non-2xx response.
 * @param {string} url
 * @param {RequestInit} [init] passed to fetch unchanged
 * @param {(res: Response) => string} [message] the thrown Error's message
 *   (default `HTTP <status>`)
 * @returns {Promise<Response>}
 */
export async function fetchOk(url, init, message = httpStatus) {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(message(res));
  return res;
}

/** fetchOk, then the body parsed as JSON. Same parameters. */
export async function fetchJson(url, init, message = httpStatus) {
  return (await fetchOk(url, init, message)).json();
}
