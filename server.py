import tornado.web
import tornado.ioloop
import tornado.options
import pymongo
import logging
import uuid

from itertools import zip_longest

db = pymongo.MongoClient()

class API:
    def __init__(self, db, base_language):
        self.db = pymongo.MongoClient()
        self.base_lang = base_language

    def create_base_article(self, path, title, lines):
        db.polyglot.articles.insert({
            "lang": self.base_lang,
            "title": title,
            "path": path,
            "content": [
                {"rev": uuid.uuid4().hex, "data": line} for line in lines ]
        })

    def create_article(self, language, path, title, lines=None):
        if language == self.base_lang:
            if lines is None:
                lines = []
            self.create_base_article(path, title, lines)
            return

        line_count = len(self.get_base_article(path)['content'])

        db.polyglot.articles.insert({
            "lang": language,
            "title": title,
            "path": path,
            "content": [
                {"rev": None} for _ in range(line_count) ]
        })

    def update_article(self, lang, path, changes, length=None):
        base_article = self.get_base_article(path)

        if lang == self.base_lang:
            """
            Set the updates first, deletes second.
            """

            sets = {}
            unsets = {}
            max_ = -1

            for index, data in changes:
                if data is None:
                    # Delete the line.
                    unsets['content.%d' % index] = None
                else:
                    if index > max_:
                        max_ = index
                    sets['content.%d' % index] = {
                            "data": data,
                            "rev": uuid.uuid4().hex
                        }

            logging.debug(changes)

            # 1. Unset the things
            if len(unsets) > 0:
                self.db.polyglot.articles.update({"path": path}, {
                        "$set": unsets
                    })

            # 2. update the thing
            if len(sets) > 0:
                self.db.polyglot.articles.update({"path": path, "lang": lang}, {
                        "$set": sets
                    })

            # 2a. check if new lines added
                diff = max_ + len(unsets) - len(base_article['content'])
                logging.debug(diff)

                if diff > 0:
                    self.db.polyglot.articles.update({"path": path, "lang": {"$ne": lang}}, {
                        "$push": { "content": {
                              "$each": [ { "rev": None } for _ in range(diff) ]
                        }}
                    })

            # 3. Delete the nulls.
            self.db.polyglot.articles.update({"path": path}, {
                    "$pull": {"content": None}
                })

        else:
            chgs = {}

            for index, data in changes:
                base_content = base_article['content'][index]
                base_rev = base_content['rev']

                chgs['content.%d' % index] = {
                        "rev": base_rev,
                        "data": data
                    }

            self.db.polyglot.articles.update({"lang": lang, "path": path}, {
                    "$set": chgs
                })

    def get_article_languages(self, path):
        return [record['lang'] for record in self.db.polyglot.articles.find({
            "path": path
        })]

    def get_article(self, language, path):
        base_record = self.get_base_article(path)

        if base_record is None:
            return None

        record = self.db.polyglot.articles.find_one({
            "path": path,
            "lang": language
        })

        if record is None:
            return None

        content = []

        for bl, l in zip_longest(base_record['content'], record['content']):
            if l['rev'] is None:
                bl['untranslated'] = True
                bl['base_data'] = bl['data']
                bl['data'] = None
                content.append(bl)
            elif bl['rev'] != l['rev']:
                l['stale'] = True
                l['base_data'] = bl['data']
                content.append(l)
            else:
                content.append(l)

        return {
            "path": path,
            "title": record['title'],
            "lang": language,
            "content": content
        }

    def get_base_article(self, path):
        record = self.db.polyglot.articles.find_one({
            "path": path,
            "lang": self.base_lang
        })

        if record is None:
            return None

        return record

api = API(db, 'en')

class BaseHandler(tornado.web.RequestHandler):
    pass

class AdminHandler(BaseHandler):
    pass

class PageHandler(BaseHandler):
    def post(self, iso639, path):
        line = self.get_body_argument('line')
        if line is not None:
            # edit mode!
            api.update_article(iso639, path, [(int(line), self.get_body_argument('data'))])
        else:
            title = self.get_body_argument('title')
            # TODO check title validity

            api.create_article(iso639, path, title)
        self.get(iso639, path)

    def get(self, iso639, path):
        record = api.get_article(iso639, path)

        langs = api.get_article_languages(path)

        if record is None:
            self.render('create.html',
                    path=path,
                    cur_lang=iso639,
                    langs=langs + [iso639])
            return

        self.render('article.html',
                title=record['title'],
                path=path,
                content=record['content'],
                cur_lang=iso639,
                langs=langs)

routes = (
    (r"/admin", AdminHandler),
    (r"/([a-z]{2,3})/(.*)", PageHandler)
)

def main():
    tornado.options.parse_command_line()

    db.polyglot.articles.remove({})

    api.create_base_article("test-article", "Test Article", [
            "This is the first para.",
            "This is the second para.",
            "This is the third para."
        ])

    api.create_article("fr", "test-article", "Article de test")

    api.update_article("fr", "test-article", [
        (1, "C'est le oneieme ligne."),
        (2, "C'est le lolieme ligne.")
    ])

    api.update_article("en", "test-article", [
        (3, "A new line has appeared."),
        (0, None)
    ])

    api.update_article("en", "test-article", [
        (3, "A new line has appeared."),
    ])

    api.update_article("fr", "test-article", [
        (1, "French final update"),
        (3, "French final update")
    ])

    api.create_article("de", "test-article", "Testartikel")

    logging.debug(db.polyglot.articles.find_one({"path": "test-article", "lang": "en"}))
    logging.debug(db.polyglot.articles.find_one({"path": "test-article", "lang": "fr"}))

    logging.debug("%r" % api.get_article("fr", "test-article"))
    app = tornado.web.Application(routes, template_path="templates")

    app.listen(8888, xheaders=True)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
    main()
