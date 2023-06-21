from __future__ import annotations

from typing import ClassVar
import dataclasses
from dataclasses import dataclass, field
import datetime
import asyncio

import aiohttp
from pyquery import PyQuery as pq
from loguru import logger

from .serialization import DataclassSerialize

ItemId = tuple[datetime.datetime, str]


NAMESPACES = {
    'calendarEvent':'https://www.mansfieldtexas.gov/Calendar.aspx',
}


def get_text(elem, selector) -> str:
    if 'calendarEvent:' in selector:
        sub_elem = get_calendarEvent_elem(elem, selector)
    else:
        sub_elem = elem(selector).eq(0)
    return sub_elem.text().strip(' ')

def parse_dt(dt_str: str) -> datetime.datetime:
    # Wed, 02 Sep 2020 20:36:22 -0600
    dt_fmt = '%a, %d %b %Y %H:%M:%S %z'
    dt = datetime.datetime.strptime(dt_str, dt_fmt)
    return dt.replace(tzinfo=None)

def parse_calenderEvent_dt(date_str: str, time_str: str) -> datetime.datetime:
    dt_fmt = '%B %d, %Y %I:%M %p'
    m, d, y = date_str.split(' ')
    d = int(d.rstrip(','))
    date_str = f'{m} {d:02d}, {y}'
    return datetime.datetime.strptime(f'{date_str} {time_str}', dt_fmt)


def get_calendarEvent_elem(src_elem, tag_name):
    if ':' in tag_name:
        tag_name = tag_name.split(':')[1]
    src_tag = src_elem[0].tag
    for i, e in enumerate(src_elem[0]):
        if e.tag.endswith(tag_name):
            return src_elem(f'{src_tag} > *').eq(i)
    raise KeyError()


@dataclass
class Feed(DataclassSerialize):
    title: str
    link: str
    build_date: datetime.datetime
    description: str
    items: dict[ItemId, FeedItem] = field(default_factory=dict)
    items_by_index: dict[int, FeedItem] = field(default_factory=dict)

    def _serialize(self) -> dict:
        data = super()._serialize()
        data['items'] = list(self.items.values())
        del data['items_by_index']
        return data

    @classmethod
    def _get_deserialize_kwargs(cls, data: dict) -> dict:
        kw = super()._get_deserialize_kwargs(data)
        items = kw['items']
        kw['items_by_index'] = {item.index:item for item in items}
        kw['items'] = {item.id:item for item in items}
        return kw

    @classmethod
    def from_xml_str(cls, xml_str: str) -> Feed:
        doc = pq(xml_str, parser='xml', namespaces=NAMESPACES)
        return cls.from_pq(doc)

    @classmethod
    def from_pq(cls, doc: pq) -> Feed:
        kw = cls._kwargs_from_pq(doc)
        obj = cls(**kw)
        item_cls = cls._get_item_class()
        for item_index, item_el in enumerate(doc('channel > item').items()):
            item = item_cls.from_pq(item_el, item_index)
            obj.add_item(item)
        return obj

    @classmethod
    def _kwargs_from_pq(cls, doc: pq) -> dict:
        chan = doc('channel').eq(0)
        kw = dict(
            title=get_text(chan, 'title'),
            link=get_text(chan, 'link'),
            build_date=parse_dt(get_text(chan, 'lastBuildDate')),
            description=get_text(chan, 'description'),
        )
        return kw

    @classmethod
    def _get_item_class(cls):
        return FeedItem

    def add_item(self, item: FeedItem):
        if item.id in self.items:
            assert self.items[item.id] == item
        if item.index in self.items_by_index:
            assert self.items_by_index[item.index] == item
        assert item.id not in self.items
        assert item.index not in self.items_by_index
        self.items[item.id] = item
        self.items_by_index[item.index] = item

    def update_from_xml_str(self, xml_str: str) -> bool:
        doc = pq(xml_str, parser='xml')
        return self.update_from_pq(doc)

    def _check_attrs_changed(self, **kwargs) -> bool:
        return {k:v for k,v in kwargs.items() if getattr(self, k) != v}

    @logger.catch
    def update_from_pq(self, doc: pq) -> bool:
        orig_build_date = self.build_date
        kw = self._kwargs_from_pq(doc)
        changed = False
        changed_attrs = self._check_attrs_changed(**kw)
        for key, val in changed_attrs.items():
            setattr(self, key, val)
            if key != 'build_date':
                changed = True

        item_cls = self._get_item_class()

        for item_index, item_el in enumerate(doc('channel > item').items()):
            # logger.debug(f'{item_index=}')
            item = item_cls.from_pq(item_el, item_index)
            index_changed = False
            if item.id in self.items:
                # logger.debug('id exists')
                existing_item = self.items[item.id]
                if item == existing_item:
                    # logger.debug('no change')
                    continue
                index_changed = item.index != existing_item.index
                if self.items_by_index[existing_item.index] is existing_item:
                    # logger.debug(f'existing_item index exists: {existing_item.index=}')
                    assert existing_item.index > item.index
                    del self.items_by_index[existing_item.index]
                _changed = existing_item.update_from_other(item)
                # logger.debug(f'item update: {_changed=}')
                if _changed:
                    changed = True
                if index_changed:
                    self.items_by_index[item.index] = existing_item
                continue
            if item.index in self.items_by_index:
                existing_item = self.items_by_index[item.index]
                if existing_item.id != item.id:
                    # logger.debug(f'index exists: {existing_item.index=}')
                    assert existing_item.index > item.index
                    del self.items_by_index[item.index]

            # logger.debug('add_item')
            self.add_item(item)
            changed = True
        if not changed:
            self.build_date = orig_build_date
        return changed

    def __iter__(self):
        for ix in sorted(self.items_by_index):
            yield self.items_by_index[ix]

@dataclass
class FeedItem(DataclassSerialize):
    title: str
    pub_date: datetime.datetime
    description: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    index: int
    use_description: ClassVar[bool] = False

    @property
    def id(self) -> ItemId:
        return self.start_time, self.title

    @classmethod
    def from_pq(cls, elem: pq, index_: int) -> FeedItem:
        kw = cls._kwargs_from_pq(elem)
        kw.setdefault('index', index_)
        return cls(**kw)

    @classmethod
    def _kwargs_from_pq(cls, elem: pq) -> dict:
        kw = dict(
            title=get_text(elem, 'title'),
            pub_date=parse_dt(get_text(elem, 'pubDate')),
            description=get_text(elem, 'description'),
        )
        evt_times = get_text(elem, 'calendarEvent:EventTimes').split(' - ')
        evt_dates = get_text(elem, 'calendarEvent:EventDates')
        if ' - ' in evt_dates:
            evt_dates = evt_dates.split(' - ')
        else:
            evt_dates = [evt_dates, evt_dates]
        for i, key in enumerate(['start_time', 'end_time']):
            kw[key] = parse_calenderEvent_dt(evt_dates[i], evt_times[i])
        return kw

    def update(self, **kwargs) -> bool:
        changed = False
        for key, val in kwargs.items():
            if getattr(self, key) == val:
                continue
            setattr(self, key, val)
            changed = True
        return changed

    def update_from_other(self, other: FeedItem) -> bool:
        changed = True
        for f in dataclasses.fields(self):
            self_val, oth_val = getattr(self, f.name), getattr(other, f.name)
            if self_val == oth_val:
                continue
            setattr(self, f.name, oth_val)
            changed = True
        return changed

@dataclass
class MeetingsFeed(Feed):
    @classmethod
    def _get_item_class(cls):
        return MeetingsFeedItem

    def __iter__(self):
        for ix in sorted(self.items_by_index):
            item = self.items_by_index[ix]
            if item.address != '1200 E. Broad St.':
                continue
            yield item

@dataclass
class MeetingsFeedItem(FeedItem):
    address: str
    city: str

    @classmethod
    def _kwargs_from_pq(cls, elem: pq) -> dict:
        kw = super()._kwargs_from_pq(elem)
        location = get_text(elem, 'calendarEvent:Location')
        kw['address'], kw['city'] = location.split('<br>')
        return kw


@dataclass
class CalendarFeed(Feed):
    @classmethod
    def _get_item_class(cls):
        return CalendarFeedItem

@dataclass
class CalendarFeedItem(FeedItem):
    description_list: list[DescriptionItem] = field(default_factory=list)
    use_description: ClassVar[bool] = True

    @classmethod
    def from_pq(cls, elem: pq, index_: int) -> FeedItem:
        obj = super().from_pq(elem, index_)
        desc_txt = obj.description
        while '<strong>' in desc_txt:
            title = desc_txt.split('<strong>')[1].split('</strong>')[0]
            desc_txt = '</strong>'.join(desc_txt.split('</strong>')[1:])
            item_desc = desc_txt.split('<strong>')[0]
            obj.add_description_item(title, item_desc)

        return obj

    def add_description_item(self, title: str, desc: str) -> DescriptionItem:
        item = DescriptionItem.create(title=title, content_text=desc)
        self.description_list.append(item)
        return item

@dataclass
class DescriptionItem(DataclassSerialize):
    title: str
    content_lines: list[str]

    @classmethod
    def create(cls, title: str, content_text: str) -> DescriptionItem:
        title = title.strip(' ')
        content_text = content_text.strip(' ')
        lines = []
        for s in content_text.split('<br>'):
            s = s.strip(' ')
            if len(s):
                lines.append(s)
        return cls(title=title, content_lines=lines)
