import unittest

from backend.news.article import (
    ArticleParserRegistry,
    GenericArticleParser,
    TencentNewsParser,
    TencentSearchNewsParser,
)


class ArticleParserTests(unittest.TestCase):
    def test_tencent_search_news_page(self):
        html = """
        <div class="article-title">收评：指数上涨</div>
        <div class="article-user-right-title"><div>财联社</div></div>
        <div class="article-content"><p>第一段。</p><p>第二段。</p></div>
        """
        result = ArticleParserRegistry().parse(
            "https://so.html5.qq.com/page/real/search_news?docid=1",
            html,
        )
        self.assertEqual(result["parser"], "tencent_search_news")
        self.assertEqual(result["title"], "收评：指数上涨")
        self.assertEqual(result["source"], "财联社")
        self.assertEqual(result["content"], "第一段。 第二段。")

    def test_tencent_news_page(self):
        html = """
        <html>
          <head><title>财联社6月18日早间新闻精选_腾讯新闻</title></head>
          <body>
            <h1 id="article-title">财联社6月18日早间新闻精选</h1>
            <p class="media-name">财联社</p>
            <div id="article-content">
              <div class="rich_media_content">
                <section>第一条新闻。<span>第二条新闻。</span></section>
                <style>.rich_media_content { color: red; }</style>
                <script>window.noise = "不要保存";</script>
              </div>
            </div>
          </body>
        </html>
        """
        result = ArticleParserRegistry().parse(
            "https://new.qq.com/rain/a/20260618A0215I00",
            html,
        )
        self.assertEqual(result["parser"], "tencent_news")
        self.assertEqual(result["title"], "财联社6月18日早间新闻精选")
        self.assertEqual(result["source"], "财联社")
        self.assertEqual(result["content"], "第一条新闻。第二条新闻。")

    def test_registry_falls_back_when_specific_parser_has_no_content(self):
        class EmptyParser(TencentNewsParser):
            def parse(self, url, html):
                return {"title": "空", "source": "", "content": ""}

        registry = ArticleParserRegistry(
            [EmptyParser(), GenericArticleParser()]
        )
        result = registry.parse(
            "https://new.qq.com/example",
            "<main><h1>通用标题</h1><p>通用正文。</p></main>",
        )
        self.assertEqual(result["parser"], "generic")
        self.assertEqual(result["content"], "通用标题 通用正文。")

    def test_registry_accepts_custom_parser_order(self):
        registry = ArticleParserRegistry(
            [TencentSearchNewsParser(), GenericArticleParser()]
        )
        result = registry.parse(
            "https://example.com/article",
            "<article><h1>标题</h1><p>正文。</p></article>",
        )
        self.assertEqual(result["parser"], "generic")
        self.assertEqual(result["title"], "标题")
        self.assertEqual(result["content"], "标题 正文。")


if __name__ == "__main__":
    unittest.main()
