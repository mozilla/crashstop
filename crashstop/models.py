# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata import utils as lmdutils
import sqlalchemy.dialects.postgresql as pg
import pytz
import six
from . import signatures, utils
from . import db, app
from .logger import logger


CHANNEL_TYPE = db.Enum(*utils.get_channels(), name='CHANNEL_TYPE')
PRODUCT_TYPE = db.Enum(*utils.get_products(), name='PRODUCT_TYPE')


class Buildid(db.Model):
    __tablename__ = 'buildid'

    product = db.Column(PRODUCT_TYPE, primary_key=True)
    channel = db.Column(CHANNEL_TYPE, primary_key=True)
    buildid = db.Column(db.DateTime(timezone=True), primary_key=True)
    version = db.Column(db.String(12))

    def __init__(self, product, channel, buildid, version):
        self.product = product
        self.channel = channel
        self.buildid = buildid
        self.version = version

    @staticmethod
    def add_buildids(data, commit=True):
        for prod, i in data.items():
            for chan, j in i.items():
                q = db.session.query(Buildid).filter(Buildid.product == prod,
                                                     Buildid.channel == chan)
                q.delete()
                for d, v in j:
                    db.session.add(Buildid(prod, chan, d, v))
        if commit:
            db.session.commit()

    @staticmethod
    def get_versions(products=utils.get_products(),
                     channels=utils.get_channels()):
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
            d[buildid] = bid.version
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
    product = db.Column(PRODUCT_TYPE, primary_key=True)
    channel = db.Column(CHANNEL_TYPE, primary_key=True)
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
    def put_data(data, bids, ratios):
        logger.info('Put signatures in db: started.')
        GlobalRatio.put_data(ratios, commit=False)
        Buildid.add_buildids(bids, commit=True)

        for product, i in data.items():
            for chan, j in i.items():
                db.session.query(Signatures).filter_by(product=product,
                                                       channel=chan).delete()
                db.session.commit()
                for sgn, infos in j.items():
                    for info in infos:
                        bugid = info['bugid']
                        numbers = info['numbers']
                        pushdate = info['pushdate']
                        success = info['success']
                        raw, installs = utils.get_raw_installs(numbers)
                        s = Signatures(product, chan, sgn, bugid, raw,
                                       installs, pushdate, success)
                        db.session.add(s)
                    db.session.commit()

        logger.info('Put signatures in db: finished.')

    # TODO: gere pc
    @staticmethod
    def get_bypc(product, channel, filt):
        query = db.session.query(Signatures)
        if filt == 'all':
            sgns = query.filter_by(product=product,
                                   channel=channel)
        else:
            sgns = query.filter_by(product=product,
                                   channel=channel,
                                   success=filt == 'successful')

        versions = Buildid.get_versions(product, channel)

        d = {}
        res = {'signatures': d,
               'versions': versions[product][channel]}

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


def put_data(date='today'):
    logger.info('Get data: started.')
    data, bids, ratios = signatures.get(date=date)
    Signatures.put_data(data, bids, ratios)
    logger.info('Get data: finished.')


def update(date='today'):
    d = lmdutils.get_date(date)
    logger.info('Update data for {}: started.'.format(d))
    put_data(date=date)
    logger.info('Update data for {}: finished.'.format(d))


def create(date='today'):
    engine = db.get_engine(app)
    if not engine.dialect.has_table(engine, 'buildid'):
        d = lmdutils.get_date(date)
        logger.info('Create data for {}: started.'.format(d))
        db.create_all()
        put_data(date=date)
        logger.info('Create data for {}: finished.'.format(d))
