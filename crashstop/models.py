# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict
import sqlalchemy.dialects.postgresql as pg
from sqlalchemy import and_, or_
import pytz
import six
from . import utils
from . import db, app
from .logger import logger


CHANNEL_TYPE = db.Enum(*utils.get_channels(), name='CHANNEL_TYPE')
PRODUCT_TYPE = db.Enum(*utils.get_products(), name='PRODUCT_TYPE')


class Lastdate(db.Model):
    __tablename__ = 'lastdate'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime(timezone=True))

    def __init__(self, date):
        self.id = 0
        self.date = date

    @staticmethod
    def set(date):
        last = db.session.query(Lastdate).first()
        if last:
            last.date = date
        else:
            last = Lastdate(date)
        db.session.add(last)
        db.session.commit()

    @staticmethod
    def get():
        last = db.session.query(Lastdate).first()
        if last:
            return last.date.astimezone(pytz.utc)
        return None


class Buildid(db.Model):
    __tablename__ = 'buildid'

    product = db.Column(PRODUCT_TYPE, primary_key=True)
    channel = db.Column(CHANNEL_TYPE, primary_key=True)
    buildid = db.Column(db.DateTime(timezone=True), primary_key=True)
    version = db.Column(db.String(12))
    unique = db.Column(db.Boolean)
    unique_prod = db.Column(db.Boolean)

    def __init__(self, product, channel, buildid, version, unique, unique_prod):
        self.product = product
        self.channel = channel
        self.buildid = buildid
        self.version = version
        self.unique = unique
        self.unique_prod = unique_prod

    @staticmethod
    def add_buildids(data, commit=True):
        if not data:
            return

        qs = db.session.query(Buildid)
        here = defaultdict(lambda: defaultdict(lambda: set()))
        for q in qs:
            here[q.product][q.channel].add(q.buildid)
        for prod, i in data.items():
            here_p = here[prod]
            for chan, j in i.items():
                here_pc = here_p[chan]
                for b, v, u, up in j:
                    if b not in here_pc:
                        db.session.add(Buildid(prod, chan, b, v, u, up))
                    else:
                        here_pc.remove(b)

                if here_pc:
                    q = db.session.query(Buildid)
                    q = q.filter(Buildid.product == prod,
                                 Buildid.channel == chan,
                                 Buildid.buildid.in_(list(here_pc)))
                    q.delete(synchronize_session='fetch')
        if commit:
            db.session.commit()

    @staticmethod
    def get_versions(products=utils.get_products(),
                     channels=utils.get_channels(),
                     unicity=False):
        if isinstance(products, six.string_types):
            products = [products]
        if isinstance(channels, six.string_types):
            channels = [channels]

        res = {p: {c: {} for c in channels} for p in products}
        bids = db.session.query(Buildid).filter(Buildid.product.in_(products),
                                                Buildid.channel.in_(channels))
        for bid in bids:
            d = res[bid.product][bid.channel]
            buildid = bid.buildid.astimezone(pytz.utc)
            if unicity:
                d[buildid] = (bid.version, bid.unique, bid.unique_prod)
            else:
                d[buildid] = bid.version
        return res

    @staticmethod
    def get_max():
        q = db.session.query(db.func.max(Buildid.buildid)).first()
        if q and q[0]:
            return q[0].astimezone(pytz.utc)
        return None

    @staticmethod
    def get_buildids(products=utils.get_products(),
                     channels=utils.get_channels()):
        if isinstance(products, six.string_types):
            products = [products]
        if isinstance(channels, six.string_types):
            channels = [channels]

        qs = db.session.query(Buildid)
        qs = qs.filter(Buildid.product.in_(products),
                       Buildid.channel.in_(channels)).order_by(Buildid.buildid)
        res = defaultdict(lambda: defaultdict(lambda: list()))
        for q in qs:
            res[q.product][q.channel].append((q.buildid.astimezone(pytz.utc),
                                              q.version))
        return res


class GlobalRatio(db.Model):
    __tablename__ = 'globalratio'

    product = db.Column(PRODUCT_TYPE, primary_key=True)
    channel = db.Column(CHANNEL_TYPE, primary_key=True)
    ratio = db.Column(db.Float)

    def __init__(self, product, channel, ratio):
        self.product = product
        self.channel = channel
        self.ratio = ratio

    @staticmethod
    def put_data(data, commit=True):
        db.session.query(GlobalRatio).delete()
        for prod, i in data.items():
            for chan, ratio in i.items():
                ins = pg.insert(GlobalRatio).values(product=prod,
                                                    channel=chan,
                                                    ratio=ratio)
                upd = ins.on_conflict_do_update(index_elements=['product',
                                                                'channel'],
                                                set_=dict(ratio=ratio))
                db.session.execute(upd)
        if commit:
            db.session.commit()


class Signatures(db.Model):
    __tablename__ = 'signatures'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product = db.Column(PRODUCT_TYPE)
    channel = db.Column(CHANNEL_TYPE)
    signature = db.Column(db.String(512))
    bugid = db.Column(db.Integer, default=0)
    raw = db.Column(pg.ARRAY(db.Integer))
    installs = db.Column(pg.ARRAY(db.Integer))
    pushdate = db.Column(db.DateTime(timezone=True))
    success = db.Column(db.Boolean)

    def __init__(self, product, channel, signature,
                 bugid, raw, installs, pushdate, success):
        self.product = product
        self.channel = channel
        self.signature = signature
        self.bugid = bugid
        self.raw = raw
        self.installs = installs
        self.pushdate = pushdate
        self.success = success

    @staticmethod
    def clean(date_ranges):
        ands = []
        for chan, rg in date_ranges.items():
            md, Md = rg
            ands.append(and_(Signatures.channel == chan,
                             Signatures.pushdate < md))
        if ands:
            q = db.session.query(Signatures).filter(or_(*ands))
            q.delete()
            db.session.commit()

    @staticmethod
    def get_pushdates():
        res = defaultdict(lambda: defaultdict(lambda: dict()))
        qs = db.session.query(Signatures)
        for q in qs:
            res[q.signature][q.bugid][q.channel] = q.pushdate
        return res

    @staticmethod
    def put_data(data, bids, ratios):
        logger.info('Put signatures in db: started.')
        GlobalRatio.put_data(ratios, commit=False)
        Buildid.add_buildids(bids, commit=True)

        for product, i in data.items():
            for chan, j in i.items():
                for sgn, infos in j.items():
                    for info in infos:
                        bugid = info['bugid']
                        numbers = info['numbers']
                        pushdate = info['pushdate']
                        success = info['success']
                        raw, installs = utils.get_raw_installs(numbers)
                        s = db.session.query(Signatures)
                        s = s.filter_by(product=product,
                                        channel=chan,
                                        signature=sgn,
                                        bugid=bugid,
                                        pushdate=pushdate).first()
                        if s:
                            added = False
                            if s.raw != raw:
                                s.raw = raw
                                added = True
                            if s.installs != installs:
                                s.installs = installs
                                added = True
                            if s.success != success:
                                s.success = success
                                added = True
                            if added:
                                db.session.add(s)
                        else:
                            s = Signatures(product, chan, sgn, bugid, raw,
                                           installs, pushdate, success)
                            db.session.add(s)
                    db.session.commit()

        logger.info('Put signatures in db: finished.')

    @staticmethod
    def get_bypc(product, channel, filt):
        versions = Buildid.get_versions(product, channel)
        versions = versions[product][channel]
        vs = sorted(versions.keys())
        max_date = vs[-1]
        min_date = vs[0]

        query = db.session.query(Signatures)
        if filt == 'all':
            sgns = query.filter(Signatures.product == product,
                                Signatures.channel == channel,
                                Signatures.pushdate <= max_date,
                                Signatures.pushdate >= min_date)
        else:
            sgns = query.filter(Signatures.product == product,
                                Signatures.channel == channel,
                                Signatures.pushdate <= max_date,
                                Signatures.pushdate >= min_date,
                                Signatures.success.is_(filt == 'successful'))

        d = {}
        res = {'signatures': d,
               'versions': versions}

        for sgn in sgns:
            d[sgn.signature] = {'bugid': sgn.bugid,
                                'pushdate': sgn.pushdate.astimezone(pytz.utc),
                                'raw': sgn.raw,
                                'installs': sgn.installs,
                                'success': sgn.success}

        return res

    @staticmethod
    def get_bybugid(bugid):
        q = db.session.query(Signatures.product, Signatures.channel,
                             Signatures.signature, Signatures.raw,
                             Signatures.installs, Signatures.pushdate,
                             Signatures.success)
        sgns = q.filter_by(bugid=bugid)

        data = {}
        versions = {}
        res = {'data': data,
               'versions': versions}
        cache = {}

        for sgn in sgns:
            prod, chan = sgn.product, sgn.channel
            if prod not in res:
                res[prod] = {}
            if chan not in res[prod]:
                res[prod][chan] = {}
            t = (prod, chan)
            if t not in versions:
                v = Buildid.get_versions(*t)[prod][chan]
                d = sorted(v.keys())
                cache[t] = d
                versions[t] = v

            dates = cache[t]
            pushdate = sgn.pushdate.astimezone(pytz.utc)
            if prod not in data:
                data[prod] = {}
            if chan not in data[prod]:
                data[prod][chan] = {}
            data[prod][chan][sgn.signature] = {'pushdate': pushdate,
                                               'dates': dates,
                                               'raw': sgn.raw,
                                               'installs': sgn.installs,
                                               'success': sgn.success}
        return res


def clear():
    db.drop_all()
    db.session.commit()


def create():
    engine = db.get_engine(app)
    if not engine.dialect.has_table(engine, 'buildid'):
        db.create_all()
