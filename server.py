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
            inserts = {}
            pushes = []
            max_ = len(base_article['content'])

            for mode, index, data in changes:
                if mode == 0: # update or delete
                    if index >= max_:
                        raise Exception("No.")

                    if data is None:
                        # Delete the line.
                        unsets['content.%d' % index] = None
                    else:
                        sets['content.%d' % index] = {
                                "data": data,
                                "rev": uuid.uuid4().hex
                            }

                elif mode == 1: # append
                    # Append to end!
                    pushes.append({"rev": uuid.uuid4().hex, "data": data})

                elif mode == 2: # insert
                    inserts[index] = { "data": data, "rev": uuid.uuid4().hex }

            logging.debug(changes)

            # 1. Unset the things
            if len(unsets) > 0:
                self.db.polyglot.articles.update({"path": path}, {
                        "$unset": unsets
                    }, multi=True)

            # 2. update the thing
            if len(sets) > 0:
                self.db.polyglot.articles.update({"path": path, "lang": lang}, {
                        "$set": sets
                    })

            # 2a. check if new lines added
            if len(pushes) > 0:
                self.db.polyglot.articles.update({"path": path, "lang": lang}, {
                        "$push": { "content": { "$each": pushes } }
                    })

                self.db.polyglot.articles.update({"path": path, "lang": {"$ne": lang}}, {
                    "$push": { "content": {
                          "$each": [ { "rev": None } for _ in pushes ]
                    }}
                }, multi=True)
            # 2b. check if inserts
            if len(inserts) > 0:
                for pos, val in inserts.items():
                    self.db.polyglot.articles.update({"path": path, "lang": lang}, {
                            "$push": {
                                "content": {
                                    "$each": [val], "$position": pos }
                            }
                        })

                    self.db.polyglot.articles.update({"path": path, "lang": {"$ne": lang}}, {
                        "$push": { "content": {
                              "$each": [ { "rev": None } ],
                              "$position": pos
                        }}
                    }, multi=True)

            # 3. Delete the nulls.
            if len(unsets) > 0:
                self.db.polyglot.articles.update({"path": path}, {
                        "$pull": {"content": None}
                    }, multi=True)
        else:
            chgs = {}

            for mode, index, data in changes:
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

        total = 0
        stale = 0
        untranslated = 0

        for bl, l in zip_longest(base_record['content'], record['content']):
            total += 1
            if l['rev'] is None:
                untranslated += 1
                bl['untranslated'] = True
                bl['base_data'] = bl['data']
                bl['data'] = None
                content.append(bl)
            elif bl['rev'] != l['rev']:
                stale += 1
                l['stale'] = True
                l['base_data'] = bl['data']
                content.append(l)
            else:
                content.append(l)

        return {
            "path": path,
            "title": record['title'],
            "lang": language,
            "content": content,
            "translation": {
                "stale": stale,
                "untranslated": untranslated,
                "total": total
            }
        }

    def get_most_recent_articles(self, lang):
        # TODO lol.
        return self.db.polyglot.articles.find({"lang": lang})

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

class RedirectHandler(BaseHandler):
    def get(self):
        self.redirect("/%s" % api.base_lang)

class HomeHandler(BaseHandler):
    def get(self, lang):
        articles = api.get_most_recent_articles(lang)
        o = [(a['title'], a['path']) for a in articles]
        self.render('home.html', lang=lang, pages=o)

class PageHandler(BaseHandler):
    def post(self, iso639, path):
        insert = self.get_body_argument('insert', None)
        line = self.get_body_argument('line', None)
        add = self.get_body_argument('add', None)

        logging.debug(add)

        if insert is not None:
            api.update_article(iso639, path, [(2, int(line), self.get_body_argument('data'))])
        elif add is not None:
            api.update_article(iso639, path, [(1, None, self.get_body_argument('data'))])
        elif line is not None:
            # edit mode!
            api.update_article(iso639, path, [(0, int(line), self.get_body_argument('data'))])
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

        t = record['translation']
        if t['total'] == 0:
            total = "100"
        else:
            total = "%.0f" % (100 - ((t['stale'] + t['untranslated']) / t['total'] * 100))

        self.render('article.html',
                title=record['title'],
                path=path,
                content=record['content'],
                cur_lang=iso639,
                base_lang=api.base_lang,
                langs=langs,
                translation=total)

routes = (
    (r"/", RedirectHandler),
    (r"/admin", AdminHandler),
    (r"/([a-z]{2,3})", HomeHandler),
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
        (0, 1, "C'est le oneieme ligne."),
        (0, 2, "C'est le lolieme ligne.")
    ])

    api.update_article("en", "test-article", [
        (1, None, "A new line has appeared."),
        (0, 0, None)
    ])

    api.update_article("en", "test-article", [
        (1, None, "A new line has appeared."),
    ])

    api.update_article("fr", "test-article", [
        (0, 1, "French final update"),
        (0, 3, "French final update")
    ])

    api.create_article("de", "test-article", "Testartikel")

    logging.debug(db.polyglot.articles.find_one({"path": "test-article", "lang": "en"}))
    logging.debug(db.polyglot.articles.find_one({"path": "test-article", "lang": "fr"}))

    logging.debug("%r" % api.get_article("fr", "test-article"))

    api.create_base_article("ppau-platform", "Pirate Party Australia Platform", [x.strip() for x in """\
# Declaration of platform and principles

Pirate Party Australia is founded on the basic tenets of:

* Freedom of culture and speech,
* The inalienable right to liberty and privacy,
* The protection of the freedoms provided by the evolving global information society,
* The transparency of institutions, and
* The restoration of the freedoms and balance lost through the encroachment of harmful and overbearing intellectual monopolies.

As part of an international movement, we seek not only to change national laws, but to reform perceptions and effect worldwide change. We seek this democratically, through parliamentary elections and lobbying of government.

# Civil liberties

Civil liberties are essential to all of us, being a balance to the power of the state, a source of freedom and progress, and the core of civil society. History records a long fight for liberty, with even basic rights such as freedom from slavery, freedom of speech and freedom from torture won with great difficulty and frequent reverses. The digital age has provided stunning progress in this age-old struggle: many hierarchies including old-style media and government centralism have been recast or overthrown, creating space for citizen engagement and new voices.

As individuals have become more empowered, co-operation and trust between citizens and the state has become increasingly important. Trust and co-operation between citizens and the state ultimately underpin our collective security. Laws which nullify civil liberties in the name of security are counter-productive because they undermine this trust. The historical truism that security is not won through the sacrifice of liberties has never been more true than in the digital age.

## Freedom of speech and related rights

Freedom of speech is not only a key civil liberty in itself, but a safeguard for other liberties. It protects not just the right to speak out, but also the right to hear and be exposed to ideas. Racism and other offensive ideas have generally lost power most swiftly in the freest societies, where they have been most effectively refuted. However, refutation can happen only when offensive ideas are permitted expression. Restrictions on speech undermine this process and rob the public of its collective capacity to judge parties and persons on the basis of full and free information.

While laws which criminalise “offensive” or “insulting” speech[1][2] may be well-intentioned, mechanisms such as section 18C of the Racial Discrimination Act impose dangerous subjectivity into our legal system. The perpetual risk in criminalising offensiveness is that almost any form of difference or disagreement can be viewed as offensive to someone, and nations such as the UK and Canada have experienced significant abuse of such laws.[3][4][5][6] Even where protections technically exist, the mere threat of legal sanction may be sufficient to chill dialogue and speech, and recent events demonstrate that restrictions on one type of speech spread all too easily to include wider categories.[7]

Recent censorship bills also threaten to infringe free expression. The Classification (Publications, Films and Computer Games) Amendment (Terrorist Material) Bill 2007 bans "praise" for terrorist acts (which are defined vaguely and broadly),[8] while the Classification (Publications, Films and Computer Games) Amendment Bill (No. 2) 1999/2001 imposes arbitrary restrictions on viewing of a range of otherwise legal consensual activities.[9][10] We support a classification system which facilitates choice by providing information, but reject any creep into broader censorship under which citizens have such choices made on their behalf.

Freedom of speech underpins other freedoms including freedom of thought, conscience and assembly. It is past time that laws seeking to restrict these fundamentals were subject to proper consultation and debate, measurement of costs and benefits, and meaningful attempts to ascertain the likelihood of purported security threats. Fundamental principles warrant evidence-based policy.

## Justice

The legal system should err on the side of civil rights and free speech. Journalist shield laws are a key in this regard: press freedom cannot exist without the right to protect sources, and the absence of protection can result in concealment of information essential to the public interest. Although nominal shield laws exist, journalists continue to face prosecution from powerful individuals for nothing more than protecting confidentiality.[11][12] To curb this, the right to protect a source needs to be strengthened by including a right for journalists to protect the content of information passed on in addition to the identity of the source. The power of inquiries to publicly expose sources must also be curbed, since such compulsion threatens the very forms of journalistic investigation which have so often been essential to inquiries launching in the first place.

Balance and equality within the legal system can be improved by unwinding recent laws aimed at loosening thresholds for detention, search and seizure, and restoring proper judicial oversight.[13] Finally, we believe the system should embody the principle of one law for all, applied to all persons equally. The Pirate Party does not support parallel legal systems and other forms of law which impose differential standards.

## Privacy

Privacy is an essential underpinning of human dignity and free expression. It encompasses not just physical privacy, but the freedom to control your cultural presence, and manage the information and identity that surrounds you. A trusting and free democratic society cannot function without the protection of a person's private life and sphere. Surreptitious and intrusive surveillance is toxic to trust, social harmony and the integrity of the state.

The Pirate Party will always support privacy and oppose attempts to nullify it. We want a higher threshold of privacy to be codified across the totality of laws in Australia. This can be done both by introducing tougher legislative requirements for organisations retaining data, and improving options available to individuals seeking to protect their personal privacy.

In addition to supporting further protections of human dignity through the curtailing of state-sponsored surveillance, Pirate Party Australia recognises that the pervasiveness and continual expansion of private and public recording equipment pose serious implications for privacy. Free expression will be significantly curtailed if all aspects of people's lives are subject to orchestrated or ad hoc surveillance. As such, we support the enactment of a statutory tort that covers both intrusions into seclusion as well as misuse of private information.

## Dignity and freedom from pain

No liberty is more fundamental than the right to live free of pain and physical torment. We support the right of adults of sound mind, facing terminal illness, and with appropriate safeguards, to end their lives with dignity and peace if they so choose. Contrary to frequent claims, support for voluntary euthanasia is not a statement of any kind on the value of life. It encompasses no more than respect for the right of persons to decide on such weighty questions for themselves, in the context of their own private circumstances. We believe politicians should represent the views of citizens, not use political office to impose religious views into the private sphere. Bans on voluntary euthanasia create a painful legacy of unmanageable suffering, lost dignity, and the sacrifice of free choice.

* View detailed civil liberties policy text.""".split('\n\n')])
    app = tornado.web.Application(routes, template_path="templates")

    app.listen(8888, xheaders=True)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
    main()
