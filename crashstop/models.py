# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata import utils as lmdutils
import sqlalchemy.dialects.postgresql as pg
import pytz
from . import signatures
from . import db, app
from .logger import logger


class Buildid(db.Model):
    __tablename__ = 'buildid'

    pc = db.Column(db.String(3), primary_key=True)
    buildid = db.Column(db.DateTime(timezone=True), primary_key=True)
    version = db.Column(db.String(12))

    PRODS = {'Fi': 'Firefox',
             'Fe': 'FennecAndroid'}

    CHANS = {'N': 'nightly',
             'B': 'beta',
             'R': 'release'}

    def __init__(self, pc, buildid, version):
        self.pc = pc
        self.buildid = buildid
        self.version = version

    @staticmethod
    def add_buildids(data, commit=True):
        db.session.query(Buildid).delete()

        for prod, i in data.items():
            for chan, j in i.items():
                pc = Buildid.get_pc(prod, chan)
                for d, v in j.items():
                    b = Buildid(pc, d, v)
                    db.session.add(b)
        if commit:
            db.session.commit()

    @staticmethod
    def get_versions(pc):
        query = db.session.query(Buildid.buildid, Buildid.version)
        versions = query.filter_by(pc=pc)
        res = {bid.astimezone(pytz.utc): v for bid, v in versions}
        return res

    @staticmethod
    def get_pc(product, channel):
        return product[:2] + channel[0].upper()

    @staticmethod
    def get_prod_chan(pc):
        p = pc[:2]
        c = pc[-1]

        return Buildid.PRODS[p], Buildid.CHANS[c]


class Signatures(db.Model):
    __tablename__ = 'signatures'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pc = db.Column(db.String(3))
    signature = db.Column(db.String(512))
    bugid = db.Column(db.Integer, default=0)
    numbers = db.Column(pg.ARRAY(db.Integer))
    pushdate = db.Column(db.DateTime(timezone=True))

    def __init__(self, pc, signature, bugid, numbers, pushdate):
        self.pc = pc
        self.signature = signature
        self.bugid = bugid
        self.numbers = numbers
        self.pushdate = pushdate

    @staticmethod
    def put_data(data, bids):
        Buildid.add_buildids(bids, commit=False)
        db.session.query(Signatures).delete()

        for product, i in data.items():
            for chan, j in i.items():
                pc = Buildid.get_pc(product, chan)
                dates = None
                for sgn, info in j.items():
                    bugid = info['bugid']
                    numbers = info['numbers']
                    pushdate = info['pushdate']
                    if not dates:
                        dates = sorted(numbers.keys())
                    numbers = [numbers[d] for d in dates]
                    s = Signatures(pc, sgn, bugid, numbers, pushdate)
                    db.session.add(s)

        db.session.commit()

    @staticmethod
    def get_bypc(product, channel):
        pc = Buildid.get_pc(product, channel)
        sgns = db.session.query(Signatures).filter_by(pc=pc)
        versions = Buildid.get_versions(pc)

        d = {}
        res = {'signatures': d,
               'versions': versions}

        for sgn in sgns:
            d[sgn.signature] = {'bugid': sgn.bugid,
                                'pushdate': sgn.pushdate.astimezone(pytz.utc),
                                'numbers': sgn.numbers}

        return res

    @staticmethod
    def get_bybugid(bugid):
        q = db.session.query(Signatures.pc, Signatures.signature,
                             Signatures.numbers, Signatures.pushdate)
        sgns = q.filter_by(bugid=bugid)

        data = {}
        versions = {}
        res = {'data': data,
               'versions': versions}
        cache = {}
        for sgn in sgns:
            prod, chan = Buildid.get_prod_chan(sgn.pc)
            if prod not in res:
                res[prod] = {}
            if chan not in res[prod]:
                res[prod][chan] = {}
            if sgn.pc not in versions:
                v = Buildid.get_versions(sgn.pc)
                d = sorted(v.keys())
                cache[sgn.pc] = d
                versions[(prod, chan)] = v

            dates = cache[sgn.pc]
            pushdate = sgn.pushdate.astimezone(pytz.utc)
            if prod not in data:
                data[prod] = {}
            if chan not in data[prod]:
                data[prod][chan] = {}
            data[prod][chan][sgn.signature] = {'pushdate': pushdate,
                                               'dates': dates,
                                               'numbers': sgn.numbers}
        return res


def update(date='today'):
    d = lmdutils.get_date(date)
    logger.info('Update data for {}: started.'.format(d))
    data, bids = signatures.get(date=date)
    Signatures.put_data(data, bids)
    logger.info('Update data for {}: finished.'.format(d))


def create(date='today'):
    engine = db.get_engine(app)
    if not engine.dialect.has_table(engine, 'numbers_info'):
        d = lmdutils.get_date(date)
        logger.info('Create data for {}: started.'.format(d))
        db.create_all()
        data, bids = signatures.get(date=date)
        Signatures.put_data(data, bids)
        logger.info('Create data for {}: finished.'.format(d))
