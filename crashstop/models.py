# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata import utils as lmdutils
import sqlalchemy.dialects.postgresql as pg
import pytz
from . import utils
from . import signatures
from . import db, app
from .logger import logger


class NumbersInfo(db.Model):
    __tablename__ = 'numbers_info'

    pc = db.Column(db.String(3), primary_key=True)
    dates = db.Column(pg.ARRAY(db.DateTime(timezone=True)))

    PRODS = {'Fi': 'Firefox',
             'Fe': 'FennecAndroid'}

    CHANS = {'N': 'nightly',
             'B': 'beta',
             'R': 'release'}

    def __init__(self, product, channel):
        self.pc = NumbersInfo.get_pc(product, channel)

    @staticmethod
    def init():
        for product in utils.get_products():
            for chan in utils.get_channels():
                n = NumbersInfo(product, chan)
                db.session.add(n)
        db.session.commit()

    @staticmethod
    def add_dates(pc, dates, commit=True):
        ni = db.session.query(NumbersInfo).filter_by(pc=pc).first()
        ni.dates = dates
        db.session.add(ni)
        if commit:
            db.session.commit()

    @staticmethod
    def get_pc(product, channel):
        return product[:2] + channel[0].upper()

    @staticmethod
    def get_prod_chan(pc):
        p = pc[:2]
        c = pc[-1]

        return NumbersInfo.PRODS[p], NumbersInfo.CHANS[c]


class Signatures(db.Model):
    __tablename__ = 'signatures'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pc = db.Column(db.String(3), db.ForeignKey('numbers_info.pc'))
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
    def put_data(data):
        olds = db.session.query(Signatures)
        for old in olds:
            db.session.delete(old)

        for product, i in data.items():
            for chan, j in i.items():
                pc = NumbersInfo.get_pc(product, chan)
                dates = None
                for sgn, info in j.items():
                    bugid = info['bugid']
                    numbers = info['numbers']
                    pushdate = info['pushdate']
                    if not dates:
                        dates = sorted(numbers.keys())
                        NumbersInfo.add_dates(pc, dates, commit=False)
                    numbers = [numbers[d] for d in dates]
                    s = Signatures(pc, sgn, bugid, numbers, pushdate)
                    db.session.add(s)

        db.session.commit()

    @staticmethod
    def get_bypc(product, channel):
        pc = NumbersInfo.get_pc(product, channel)
        dates = db.session.query(NumbersInfo.dates).filter_by(pc=pc).first()
        sgns = db.session.query(Signatures).filter_by(pc=pc)

        if dates[0]:
            dates = [d.astimezone(pytz.utc) for d in dates[0]]
        else:
            dates = []

        d = {}
        res = {'dates': dates,
               'signatures': d}

        for sgn in sgns:
            d[sgn.signature] = {'bugid': sgn.bugid,
                                'pushdate': sgn.pushdate.astimezone(pytz.utc),
                                'numbers': sgn.numbers}

        return res

    @staticmethod
    def get_bybugid(bugid):
        q = db.session.query(Signatures.pc, Signatures.signature,
                             Signatures.numbers, Signatures.pushdate,
                             NumbersInfo.dates)
        sgns = q.filter_by(bugid=bugid).join(NumbersInfo)

        res = {}
        for sgn in sgns:
            prod, chan = NumbersInfo.get_prod_chan(sgn.pc)
            if prod not in res:
                res[prod] = {}
            if chan not in res[prod]:
                res[prod][chan] = {}
            dates = [d.astimezone(pytz.utc) for d in sgn.dates]
            pushdate = sgn.pushdate.astimezone(pytz.utc)
            res[prod][chan][sgn.signature] = {'pushdate': pushdate,
                                              'dates': dates,
                                              'numbers': sgn.numbers}
        return res


def update(date='today'):
    d = lmdutils.get_date(date)
    logger.info('Update data for {}: started.'.format(d))
    data = signatures.get(date=date)
    Signatures.put_data(data)
    logger.info('Update data for {}: finished.'.format(d))


def create(date='today'):
    engine = db.get_engine(app)
    if not engine.dialect.has_table(engine, 'numbers_info'):
        d = lmdutils.get_date(date)
        logger.info('Create data for {}: started.'.format(d))
        db.create_all()
        NumbersInfo.init()
        data = signatures.get(date=date)
        Signatures.put_data(data)
        logger.info('Create data for {}: finished.'.format(d))
