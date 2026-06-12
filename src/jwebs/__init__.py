# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
from .core.http import FastHTTP, HTTPResponse, RequestRecord
from .core.exceptions import (
    JWebsError, HTTPError, JWebsConnectionError,
    JWebsTimeoutError, RobotsBlockedError, CacheError
)
from .check import Checker, SecurityReport, SEOScore, PerformanceMetrics
from .extract import Builder
from .crawl import Crawler, DistributedCrawler
from .ai import AIScrapingEngine, GraphQLClient, GraphQLResponse
from .captcha import CaptchaSolver, CAPTCHAResult
from .proxy import ProxyRotator, ProxyConfig
from .monitor import Monitor
from .smart import SmartScraper
from .async_ import AsyncClient, AsyncResponse
from .diff import ContentDiffer
from .generate import SitemapGenerator, RSSGenerator
from .jwebs import JWebs

__version__ = "1.0.0"
__author__ = "J Code"
__license__ = "Apache-2.0"