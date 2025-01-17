#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/7/24 15:35
# @Author  : pikadoramon
# @File    : main.py
# @Software: PyCharm
import argparse
import asyncio
import logging

import pandas as pd
from loguru import logger
from yt_dlp import traverse_obj

from workers.bdriver import TikTokSession, random_params

log_format = "{time:YYYY-MM-DD HH:mm:ss.SSS}|{level}|{name}|pid={process},thread={thread.name},path={file.path},func={function}|line={line},msg={message}"
logger.add(r"./playwrightTiktok.log", level=logging.INFO, format=log_format, colorize=False,
           backtrace=True, diagnose=True)


# Parse command-line arguments
def parse_args():
    parser = argparse.ArgumentParser(description="Tiktok Migrate Download Tool")
    parser.add_argument("--url", type=str, required=True,
                        help="Target URL to fetch (format: http://www.tiktok.com/@...)")
    parser.add_argument("--proxy", type=str, default=None, help="Proxy server (format: http://user:pass@proxy:port)")
    parser.add_argument("--retry", type=int, default=3, help="Maximum number of retry attempts (default: 3)")
    parser.add_argument("--delay", type=int, default=5, help="Delay between retries in seconds (default: 5)")
    parser.add_argument("--count", type=int, default=10, help="Number of requests to perform (default: 10)")
    parser.add_argument("--output", type=str, default="output.csv",
                        help="CSV filename to export data (default: output.csv)")
    return parser.parse_args()


args = parse_args()


async def main():
    global args
    logger.info(f"""
    fetch: {args.url}
    proxy: {args.proxy}
    retry: {args.retry}
    delay: {args.delay}
    count: {args.count}
    output: {args.output}
    """)
    api = TikTokSession()
    await api.create_session(
        headless=False,
        browser='firefox',
        proxy=args.proxy,
        context_options=random_params,
        disable_image=True
    )

    user = api.user(username=args.url, sec_uid=None)
    result = await user.videos_as_list(limit=args.count,
                                       sleep_after=args.delay,
                                       retry=args.retry)

    data = traverse_obj(result, ("data", "items"), default=[])
    if len(data) == 0:
        logger.info("no any datas")
        return
    df = pd.DataFrame(data)
    df.to_csv(args.output, index=False)
    logger.info("Save file: " + args.output)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    loop.run_until_complete(main())
