# -*- coding: utf-8 -*-
# 科技媒体强化：RSS 每日增量，Sitemap 回填/兜底
SOURCES = {
    "wired": {
        "display_name": "WIRED",
        "domain": "wired.com",
        "rss": [
            "https://www.wired.com/feed/rss",
            "https://www.wired.com/feed/category/business/latest/rss",
            "https://www.wired.com/feed/category/science/latest/rss",
            "https://www.wired.com/feed/category/gear/latest/rss",
        ],
        "sitemap": "https://www.wired.com/sitemap.xml",
    },
    "economist": {
        "display_name": "The Economist",
        "domain": "economist.com",
        "rss": [
            "https://www.economist.com/latest/rss.xml",
            "https://www.economist.com/finance-and-economics/rss.xml",
            "https://www.economist.com/business/rss.xml",
            "https://www.economist.com/international/rss.xml",
            "https://www.economist.com/science-and-technology/rss.xml",
            "https://www.economist.com/culture/rss.xml",
            "https://www.economist.com/europe/rss.xml",
        ],
        "sitemap": "https://www.economist.com/sitemap.xml",
    },
    "scientific_american": {
        "display_name": "Scientific American",
        "domain": "scientificamerican.com",
        "rss": ["https://www.scientificamerican.com/feed/"],
        "sitemap": "https://www.scientificamerican.com/sitemap.xml",
    },
    "the_atlantic": {
        "display_name": "The Atlantic",
        "domain": "theatlantic.com",
        "rss": ["https://www.theatlantic.com/feed/all/"],
        "sitemap": "https://www.theatlantic.com/sitemap.xml",
    },
    "nytimes": {
        "display_name": "The New York Times",
        "domain": "nytimes.com",
        "rss": [
            "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        ],
        "sitemap": "https://www.nytimes.com/sitemaps/sitemap.xml",
    },
    "wsj": {
        "display_name": "The Wall Street Journal",
        "domain": "wsj.com",
        "rss": [
            "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
            "https://feeds.a.dj.com/rss/RSSUSBusiness.xml",
            "https://feeds.a.dj.com/rss/RSSWSJD.xml",
            "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        ],
        "sitemap": "https://www.wsj.com/sitemap.xml",
    },

    # 强化科技媒体
    "ars_technica": {
        "display_name": "Ars Technica",
        "domain": "arstechnica.com",
        "rss": [
            "https://feeds.arstechnica.com/arstechnica/index",
            "https://feeds.arstechnica.com/arstechnica/technology-lab",
            "https://feeds.arstechnica.com/arstechnica/science",
            "https://feeds.arstechnica.com/arstechnica/tech-policy",
        ],
        "sitemap": "https://arstechnica.com/sitemap.xml",
    },
    "the_verge": {
        "display_name": "The Verge",
        "domain": "theverge.com",
        "rss": ["https://www.theverge.com/rss/index.xml"],
        "sitemap": "https://www.theverge.com/sitemap.xml",
    },
    "techcrunch": {
        "display_name": "TechCrunch",
        "domain": "techcrunch.com",
        "rss": ["https://techcrunch.com/feed/"],
        "sitemap": "https://techcrunch.com/sitemap.xml",
    },
    "mit_tech_review": {
        "display_name": "MIT Technology Review",
        "domain": "technologyreview.com",
        "rss": ["https://www.technologyreview.com/feed/"],
        "sitemap": "https://www.technologyreview.com/sitemap.xml",
    },
    "ieee_spectrum": {
        "display_name": "IEEE Spectrum",
        "domain": "spectrum.ieee.org",
        "rss": ["https://spectrum.ieee.org/rss/fulltext"],
        "sitemap": "https://spectrum.ieee.org/sitemap.xml",
    },
    "engadget": {
        "display_name": "Engadget",
        "domain": "engadget.com",
        "rss": ["https://www.engadget.com/rss.xml"],
        "sitemap": "https://www.engadget.com/sitemap.xml",
    },
    "new_scientist": {
        "display_name": "New Scientist",
        "domain": "newscientist.com",
        "rss": ["https://www.newscientist.com/feed/home"],
        "sitemap": "https://www.newscientist.com/sitemap.xml",
    },
    "nature": {
        "display_name": "Nature",
        "domain": "nature.com",
        "rss": ["https://www.nature.com/feeds/news.rss"],
        "sitemap": "https://www.nature.com/sitemap.xml",
    },
    "science_magazine": {
        "display_name": "Science",
        "domain": "science.org",
        "rss": [
            "https://www.science.org/rss/news_current.xml",
            "https://www.science.org/rss/table-of-contents/science.xml",
        ],
        "sitemap": "https://www.science.org/sitemap.xml",
    },
    "the_register": {
        "display_name": "The Register",
        "domain": "theregister.com",
        "rss": ["https://www.theregister.com/headlines.atom"],
        "sitemap": "https://www.theregister.com/sitemap.xml",
    },
    "zdnet": {
        "display_name": "ZDNet",
        "domain": "zdnet.com",
        "rss": ["https://www.zdnet.com/news/rss.xml"],
        "sitemap": "https://www.zdnet.com/sitemap.xml",
    },
    "gizmodo": {
        "display_name": "Gizmodo",
        "domain": "gizmodo.com",
        "rss": ["https://gizmodo.com/rss"],
        "sitemap": "https://gizmodo.com/sitemap.xml",
    },
    "venturebeat": {
        "display_name": "VentureBeat",
        "domain": "venturebeat.com",
        "rss": ["https://venturebeat.com/feed/"],
        "sitemap": "https://venturebeat.com/sitemap.xml",
    },
    "thenextweb": {
        "display_name": "The Next Web",
        "domain": "thenextweb.com",
        "rss": ["https://thenextweb.com/feed"],
        "sitemap": "https://thenextweb.com/sitemap.xml",
    },
    "pcmag": {
        "display_name": "PCMag",
        "domain": "pcmag.com",
        "rss": ["https://www.pcmag.com/feeds/rss"],
        "sitemap": "https://www.pcmag.com/sitemap.xml",
    },
    "guardian_tech": {
        "display_name": "The Guardian · Technology",
        "domain": "theguardian.com",
        "rss": ["https://www.theguardian.com/technology/rss"],
        "sitemap": "https://www.theguardian.com/sitemaps",
    },
}

# 仅保存 2025-01-01 及之后的文章
START_DATE_ISO = "2025-01-01"

# RSS 无新增，用 Sitemap 回查最近 N 小时（加大力度）
SITEMAP_LOOKBACK_HOURS = 72

# GitHub 仓库源（仅在许可证允许再分发时抓取全文）
GITHUB_REPOS = [
    {"owner": "plsy1", "repo": "emagzines", "branch": "", "roots": ["."], "exts": [".md", ".txt", ".html"], "max_files": 150},
    {"owner": "hehonghui", "repo": "awesome-english-ebooks", "branch": "", "roots": ["."], "exts": [".md", ".txt", ".html"], "max_files": 150},
]
