#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/7/23 20:12
# @Author  : pikadoramon
# @File    : tiktok_user.py
# @Software: PyCharm
import asyncio
import json
import re
import time
import traceback
from urllib.parse import urlencode

import aiohttp
from yt_dlp.utils import traverse_obj
from workers.exceptions.inject_exception import EmptyResponseError, EmptyFieldError


async def share_to_real_async(url, proxies=None, headers=None):
    """
    Asynchronously get the real link
    :param url:
    :param proxies:
    :param headers:
    :return:
    """
    status = 0
    msg = ""
    user_info = null

    if url.startswith("https://www.tiktok.com/"):
        user_info = {
            'url': url.split("?")[0]
        }
        status = 1
        msg = ""
    else:
        if not headers:
            headers = {
                "Accept-Encoding": "gzip",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.132 Safari/537.36"
            }

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, proxy=proxies, timeout=5, allow_redirects=False) as response:
                if response.status == 301:
                    real_url = response.headers["Location"].split("?")[0]
                    if real_url.startswith("https://www.tiktok.com/"):
                        user_info = {
                            'url': real_url
                        }
                        status = 1
                        msg = ""
                    elif real_url.startswith("https://m.tiktok.com/") or real_url.startswith("https://t.tiktok.com/"):
                        async with session.get(real_url, proxy=proxies, timeout=5, allow_redirects=False) as response:
                            real_url = response.headers["Location"].split("?")[0]
                            if response.status == 301 and real_url.startswith("https://www.tiktok.com/"):
                                real_url = response.headers["Location"].split("?")[0]
                                user_info = {
                                    'url': real_url
                                }
                                status = 1
                                msg = ""
                elif response.status == 302:
                    status = response.status
                    msg = "page not found"
                else:
                    status = -1
                    msg = await response.text()

    return {
        "status": status,
        "msg": msg,
        "data": user_info
    }


def serialize_fields(data):
    re_fields = [
        "WebIdLastTime",
        "browser_version",
        "device_id",
        "odinId",
        "region",
        "secUid"
    ]
    fields_rule = dict(
        WebIdLastTime='"webIdCreatedTime":"(\d+)"',
        aid='1988',
        app_language='en',
        app_name='tiktok_web',
        browser_language='en',
        browser_name='Mozilla',
        browser_online='true',
        browser_platform='Win32',
        browser_version='"userAgent":"(.+?)","',
        channel='tiktok_web',
        cookie_enabled='true',
        count='35',
        coverFormat='2',
        cursor='0',
        data_collection_enabled='true',
        device_id='"wid":"(\d+)"',
        device_platform='web_pc',
        focus_state='true',
        from_page='user',
        history_len='3',
        is_fullscreen='false',
        is_page_visible='true',
        language='en',
        needPinnedItemIds='true',
        odinId='"odinId":"(\d+)"',
        os='windows',
        post_item_list_request_type='0',
        priority_region='',
        referer='',
        region='"region":"(\w+)"',
        screen_height='1152',
        screen_width='2048',
        secUid='"secUid":"(.+?)","',
        tz_name='Asia/Shanghai',
        user_is_login='false',
    )
    empty_fields = set()
    for k in re_fields:
        value = re.search(fields_rule[k], data)
        if value:
            fields_rule[k] = value.group(1).encode('utf-8').decode('unicode-escape')
            if k == "browser_version":
                fields_rule[k] = fields_rule[k].replace("Mozilla/", "")
        else:
            empty_fields.add(k)
    if "secUid" in empty_fields and len(empty_fields) <= 1:
        return fields_rule
    if len(empty_fields) == 0:
        return fields_rule
    raise EmptyFieldError(f"empty {empty_fields} fields")


class TikTokUser:

    def __init__(self, username=None, sec_uid=None):
        self.username = username
        self.sec_uid = sec_uid
        self.params = None

    def set_username(self, username=None, sec_uid=None):
        self.username = username
        self.sec_uid = sec_uid
        self.params = None

    async def prepare_user_request(self):
        if self.sec_uid:
            url = "https://www.tiktok.com/foryou"
            response = await self.parent.make_inject_request(url)
            if not response:
                raise EmptyResponseError(f"{url} empty response body")
            params = serialize_fields(response.text)
            params["secUid"] = self.sec_uid
            self.params = params
            return

        if self.username:
            url = "https://www.tiktok.com/@" + self.username.split("@")[-1]
            response = await self.parent.make_inject_request(url)
            if not response:
                raise EmptyResponseError(f"{url} empty response body")
            if response.text.find("Please wait...") > 0:
                self.logger.warning(f"{self} xhr request failed web redirect {url}")
                await self.parent.execute_js_script(None, f"location.href = \"{url}\"")
            params = serialize_fields(response.text)
            self.params = params
            i, session = self.parent.get_session()
            await session.page.goto(url)

            return

        raise ValueError("empty user")

    async def videos(self, limit, cursor='0', retry=3, sleep_after=2):

        c = 0
        while c < retry:
            try:
                await self.prepare_user_request()
                if not self.params["secUid"].startswith("M"):
                    raise EmptyFieldError(f"{self} error secUid {self.params}")
                break
            except Exception as e:
                c += 1
                self.logger.error(f"{self} {c}/{retry} exc: {e}")
                if str(e).find("Timeout") > -1 or str(e).find("NS_ERROR_PROXY_AUTHENTICATION_FAILED") > -1:
                    self.parent.page_error = True

            await asyncio.sleep(sleep_after)
        if self.params is None:
            raise EmptyFieldError("empty user fingerprint")
        if not self.params["secUid"].startswith("M"):
            raise EmptyFieldError(f"error secUid {self.params}")

        self.logger.info("null user parameters: null".format(self, json.dumps(self.params)))
        limit = min(limit, 500)
        c = 0
        found = 0
        seen_cursors = set([])

        while found < limit:
            try:
                await asyncio.sleep(sleep_after)
                if cursor:
                    self.params["cursor"] = cursor
                seen_cursors.add(cursor)

                url = "https://www.tiktok.com/api/post/item_list/?" + urlencode(self.params)
                response = await self.parent.make_inject_request(url=url)
                if not response:
                    raise EmptyResponseError(f"{url} empty response body")
                item_list = response.json().get("itemList")
                for item in item_list:
                    found += 1
                    yield item
                cursor = response.json().get("cursor")
                if not cursor or cursor in seen_cursors:
                    self.logger.error(f"{self} cursor[{cursor}] is null or duplicated")
                    break
                c = 0
            except Exception as e:
                c += 1
                if c > retry:
                    self.logger.error(f"{self} exit {c}/{retry} exc: {e}")
                    break

                self.logger.error(f"{self} {c}/{retry} exc: {e}")
                if str(e).find("Timeout") > -1 or str(e).find("NS_ERROR_PROXY_AUTHENTICATION_FAILED") > -1:
                    self.parent.page_error = True


    async def videos_as_list(self, limit, cursor='0', retry=3, sleep_after=2):
        data = {
            "status": 1,
            "msg": "",
            "data": {
                "items": [
                ],
                "cursor_info": {
                    "user_id": None,
                    "sec_uid": None,
                    "cursor": "",
                    "lang": "",
                    "page": "",
                    "x": ""
                },
                "posts": 0,
                "has_more": False,
                "user_id": "",
                "user_name": None
            }
        }
        video_rule = {
            "id": ("id",),
            "picture_url": ("video", "cover"),
            "video_url": ("video", "bitrateInfo", 0, "PlayAddr", "UrlList", -1),
            "width": ("video", "bitrateInfo", 0, "PlayAddr", "Width"),
            "height": ("video", "bitrateInfo", 0, "PlayAddr", "Height"),
            "duration_second": ("video", "duration"),
        }
        item_rule = {
            "user_id": ("author", "id"),
            "username": ("author", "uniqueId"),
            "item_id": ("id",),
            "videos": None,
            "publish_time": ("createTime",),
            "description": ("desc",),
            "like_count": ("stats", "diggCount"),
            "download_count": ("stats", "collectCount"),
            "comment_count": ("stats", "commentCount"),
            "play_count": ("stats", "playCount"),
            "share_count": ("stats", "shareCount")
        }
        user_rule = {
            "user_id": ("author", "id"),
            "username": ("author", "uniqueId"),
            "nickname": ("author", "nickname"),
            "avatar_url": ("author", "avatarLarger"),
            "signature": ("author", "signature")
        }
        i = 0
        _inner_data = data["data"]
        async for item in self.videos(limit, cursor, retry, sleep_after):
            item_info = dict()
            author_info = dict()
            if i == 0:
                _inner_data["cursor_info"]["user_id"] = traverse_obj(item, ("author", "id"))
                _inner_data["cursor_info"]["sec_uid"] = traverse_obj(item, ("author", "secUid"))
                _inner_data["user_id"] = traverse_obj(item, ("author", "id"))
                _inner_data["user_name"] = traverse_obj(item, ("author", "uniqueId"))
            data["data"]["posts"] += 1

            i += 1
            try:
                _inner_data["cursor_info"]["cursor"] = "%d" % (traverse_obj(item, ("createTime",), default=0) * 1000)
                for e in item_rule:
                    if not isinstance(item_rule[e], tuple):
                        continue
                    value = traverse_obj(item, item_rule[e])
                    if value is None:
                        raise ValueError(f"null value {e} {item_rule[e]}")
                    item_info[e] = value

                video_info = dict()
                for e in video_rule:
                    if not isinstance(video_rule[e], tuple):
                        continue
                    value = traverse_obj(item, video_rule[e])
                    if value is None:
                        raise ValueError(f"null value {e} {video_rule[e]}")
                    video_info[e] = value

                item_info.update(video_info)

                for e in user_rule:
                    if not isinstance(user_rule[e], tuple):
                        continue
                    value = traverse_obj(item, user_rule[e])
                    if value is None:
                        raise ValueError(f"null value {e} {user_rule[e]}")
                    author_info[e] = value
                item_info.update(author_info)
                data["data"]["items"].append(
                    item_info
                )
            except Exception as e:
                self.logger.error(str(e) + " datanull=null".format(self, json.dumps(item)))

        if len(data["data"]["items"]) == 0:
            data["status"] = 0
            data["msg"] = "empty posts"
            return data
        return data

    def __repr__(self):
        if self.username:
            return "[TikTokUser username=null]".format(self.username)
        elif self.sec_uid:
            return "[TikTokUser secUid=null]".format(self.sec_uid)
        return "[TikTokUser username=undefined]"