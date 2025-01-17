#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/7/23 15:58
# @Author  : pikadoramon
# @File    : bdriver.py
# @Software: PyCharm
import asyncio
import dataclasses
import datetime
import random
import time
from base64 import b64encode
from typing import Any
from urllib.parse import urlparse

import requests
from playwright.async_api import async_playwright, Page
from requests.cookies import RequestsCookieJar

from workers.api.tiktok_user import TikTokUser
from workers.stealth import stealth_async
from loguru import logger


def decode_unicode_escapes(encoded_string):
    try:
        return encoded_string.encode('utf-8').decode('unicode-escape')
    except Exception as e:
        logger.error(f"{e} {encoded_string[:100]}")
        return encoded_string


@dataclasses.dataclass
class TikTokPlaywrightSession:
    """A TikTok session using Playwright"""

    context: Any
    page: Page
    proxy: str = None
    params: dict = None
    headers: dict = None
    ms_token: str = None
    base_url: str = "https://www.tiktok.com"

    latest_at: int = 0
    create_at: int = 0
    expired_at: int = 0


async def block_aggressively(route):
    excluded_resource_types = ["stylesheet", "image", "font", "video"]
    if route.request.resource_type in excluded_resource_types:
        await route.abort()
    else:
        await route.continue_()


class TikTokSession:
    user = TikTokUser

    def __init__(self):
        self._session_pool = []
        self._browser_type = None
        self.playwright = None
        self.browser = None
        self._page_error = False

        TikTokUser.parent = self
        TikTokUser.logger = logger

    async def create_session(
            self,
            headless=True,
            proxy: list = None,
            starting_url="https://www.tiktok.com",
            context_options: dict = {},
            override_browser_args: list = None,
            cookies: list = None,
            browser: str = "chromium",
            executable_path: str = None,
            disable_image: bool = False
    ):
        self.playwright = await async_playwright().start()
        self._browser_type = browser
        auth = None
        if proxy and isinstance(proxy, str):
            struct_url = urlparse(proxy)
            proxy = {"server": "{}://{}:{}".format(struct_url.scheme, struct_url.hostname, struct_url.port)}
            if struct_url.username and struct_url.password:
                auth = struct_url.username + ":" + struct_url.password
        logger.info("proxy={} auth={}".format(proxy, auth))
        if browser == "chromium":
            if headless and override_browser_args is None:
                override_browser_args = ["--headless=new"]
                headless = False  # managed by the arg
            self.browser = await self.playwright.chromium.launch(
                headless=headless, args=override_browser_args,
                executable_path=executable_path
            )
        elif browser == "firefox":
            self.browser = await self.playwright.firefox.launch(
                headless=headless, args=override_browser_args,
                executable_path=executable_path,
                ignore_default_args=["--mute-audio"],
            )

        else:
            raise ValueError("Invalid browser argument passed")

        context = await self.browser.new_context(proxy=proxy, **context_options)
        if auth and self._browser_type == "firefox":
            await context.set_extra_http_headers(
                {"Proxy-Authorization": "Basic " + b64encode(auth.encode()).decode("utf8")})
        if cookies is not None:
            formatted_cookies = [
                {"name": k, "value": v, "domain": urlparse(starting_url).netloc, "path": "/"}
                for k, v in cookies.items()
                if v is not None
            ]
            await context.add_cookies(formatted_cookies)
        page = await context.new_page()
        await stealth_async(page)

        request_headers = None

        def handle_request(request):
            nonlocal request_headers
            request_headers = request.headers
            if request.url.find("post"):
                print("Request", request.url)

        if disable_image:
            await page.route("**/*", block_aggressively)

        page.once("request", handle_request)
        session = TikTokPlaywrightSession(
            context,
            page,
            proxy=proxy,
            headers=request_headers,
            base_url=starting_url,
            latest_at=0,
            create_at=int(time.time()),
            expired_at=int(time.time()) + 900
        )
        self._session_pool.append(session)

    def _get_session(self):
        if len(self._session_pool) == 0:
            raise ValueError("empty session")

        i = random.randint(0, len(self._session_pool) - 1)
        self._session_pool[i].latest_at = int(time.time())
        return i, self._session_pool[i]

    async def make_inject_request(self, url=None):
        st = time.time()
        i, session = self._get_session()
        if session.page.url.find(session.base_url) == -1:
            await session.page.goto(session.base_url)
        method = 'GET'
        js_tpl = f"""
                  () => {{
                      return new Promise((resolve, reject) => {{
                            var xhr = new XMLHttpRequest();
                            xhr.open('{method}', '{url}', true);
                    
                            xhr.onload = function() {{
                                if (xhr.status >= 200 && xhr.status < 300) {{
                                    resolve(xhr.responseText);
                                }} else {{
                                    reject(xhr.statusText);
                                }}
                            }};
                    
                            xhr.onerror = function() {{
                                reject(xhr.statusText);
                            }};
                    
                            xhr.send();
                      }});
                  }}
              """
        logger.info(f"{js_tpl}")
        result = await self.execute_js_script(session, js_tpl)
        if not result:
            return ""
        res = requests.Response()
        cookie_jar = RequestsCookieJar()
        response_dict = {"_content": result.encode(), "cookies": cookie_jar, "encoding": "utf-8",
                         "headers": session.headers, "status_code": 200, "elapsed": (time.time() - st) * 1000,
                         "url": url}

        response_dict["elapsed"] = datetime.timedelta(
            0, 0, response_dict["elapsed"]
        )  # 耗时
        response_dict["connection"] = None
        response_dict["_content_consumed"] = True

        res.__dict__.update(response_dict)
        return res

    get_session = _get_session

    async def execute_js_script(self, session, js_code):
        if session is None:
            i, session = self._get_session()

        result = await session.page.evaluate(js_code)
        if not result:
            return ""
        return result


    async def close_sessions(self):
        """
        Close all the sessions. Should be called when you're done with the TikTokApi object

        This is called automatically when using the TikTokApi with "with"
        """
        for session in self._session_pool:
            await session.page.close()
            await session.context.close()

        await self.stop_playwright()

    async def __aenter__(self):
        return self

    async def stop_playwright(self):
        """Stop the playwright browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def __aexit__(self, exc_type, exc, tb):
        await self.close_sessions()
        await self.stop_playwright()

    @property
    def page_error(self):
        return self._page_error

    @page_error.setter
    def page_error(self, value):
        self._page_error = value


random_params = {
    "viewport": {"width": 2048, "height": 1152},
    "no_viewport": random.choice([False, ]),
    "ignore_https_errors": random.choice([True, False]),
    "java_script_enabled": random.choice([True, ]),
    "bypass_csp": random.choice([True, False]),
    "user_agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0',
    "locale": random.choice(["en-GB", "eu-US", "en-Au"]),
    "timezone_id": random.choice(["UTC", "America/New_York", "Asia/Tokyo"]),
    "permissions": ["geolocation", "notifications"],
    "geolocation": {"latitude": 40.7143, "longitude": -74.0060, "accuracy": random.uniform(0, 100)},

    "device_scale_factor": random.uniform(0.5, 3.0),
    "is_mobile": random.choice([False]),
    "has_touch": random.choice([True, False]),
    "color_scheme": random.choice(["dark", "light", "no-preference", "null"]),
    "reduced_motion": random.choice(["no-preference", "null", "reduce"]),
    "forced_colors": random.choice(["active", "none", "null"]),
    "accept_downloads": random.choice([False, ]),
    "default_browser_type": random.choice(["firefox", "webkit"]),

    "base_url": "https://www.tiktok.com",
    "strict_selectors": random.choice([True, ]),
    "service_workers": random.choice(["allow", "block"]),
    "record_har_url_filter": ".*example.*",
    "record_har_mode": random.choice(["full", "minimal"]),
    "record_har_content": random.choice(["attach", "embed", "omit"])
}

