# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, ElementTree
from typing import List, Dict

class SitemapGenerator:
    def GENERATE(self, urls: List[str], filepath: str = 'sitemap.xml',
                 changefreq: str = 'weekly', priority: float = 0.8) -> str:
        urlset = Element('urlset', xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')
        for url in urls:
            url_el = SubElement(urlset, 'url')
            SubElement(url_el, 'loc').text = url
            SubElement(url_el, 'lastmod').text = datetime.now().strftime('%Y-%m-%d')
            SubElement(url_el, 'changefreq').text = changefreq
            SubElement(url_el, 'priority').text = str(priority)
        tree = ElementTree(urlset)
        tree.write(filepath, encoding='utf-8', xml_declaration=True)
        return filepath


class RSSGenerator:
    def GENERATE(self, items: List[Dict], title: str, link: str,
                 description: str, filepath: str = 'feed.xml') -> str:
        rss = Element('rss', version='2.0')
        channel = SubElement(rss, 'channel')
        SubElement(channel, 'title').text = title
        SubElement(channel, 'link').text = link
        SubElement(channel, 'description').text = description
        for item in items:
            item_el = SubElement(channel, 'item')
            SubElement(item_el, 'title').text = item.get('title', '')
            SubElement(item_el, 'link').text = item.get('link', '')
            SubElement(item_el, 'description').text = item.get('description', '')
        tree = ElementTree(rss)
        tree.write(filepath, encoding='utf-8', xml_declaration=True)
        return filepath