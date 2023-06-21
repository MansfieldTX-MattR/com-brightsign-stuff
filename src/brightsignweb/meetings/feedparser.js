

async function fetchFeed(feedUrl){
    const resp = await fetch(
        feedUrl, 
        {
            mode:"no-cors",
            headers:{'Accept':'text/xml'},
        },
    );
    // if (!resp.ok){
    //     throw new Error('Request error: status=' + resp.status.toString() + ', "' + resp.statusText + '"');
    // }
    const parser = new DOMParser();
    const respText = await resp.text();
    if (!respText){
        console.log('fetch response with no content');
        return null;
    }
    const doc = parser.parseFromString(respText, 'text/xml');
    // console.log('doc: ', doc);
    return doc;
}

function parsePubDate(dtStr){
    return new Date(Date.parse(dtStr));
}

function parseCalendarEventDate(dateStr, timeStr){
    // const all_months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    // const dateSplit = dateStr.strip().split(' ');
    // const month = all_months.indexOf(dateSplit[0]);
    // let dt = new Date();
    // dt.setFullYear(parseInt(dateSplit[2]));
    // dt.setMonth(month);
    // dt.setDate(parseInt(dateSplit[2]));
    let dtStr = dateStr;
    if (timeStr !== undefined){
        dtStr = [dtStr, timeStr].join(' ');
    }
    return new Date(dtStr);
}

function getElemText(srcEl, selector){
    let el = srcEl;
    if (selector !== undefined){
        if (selector.startsWith('calendarEvent:')){
            el = getCalendarEventTag(srcEl, selector);
        } else {
            el = srcEl.querySelector(selector);
        }
    }
    return el.textContent;
}

function getCalendarEventTag(srcEl, tagName){
    for (const el of srcEl.children){
        if (el.tagName == tagName){
            return el;
        }
    }
    return null;
}

class FeedItem {
    constructor(title, pubDate, description, startTime, endTime){
        this.title = title;
        this.pubDate = pubDate;
        this.description = description;
        this.startTime = startTime;
        this.endTime = endTime;
    }

    get id() {
        // return this.startTime.valueOf();
        return `${this.title} || ${this.timeStamp}`;
    }

    get timeStamp(){
        return this.startTime.valueOf();
    }

    static parse(elem){
        const cls = this;
        const title = getElemText(elem, 'title');
        const pubDate = parsePubDate(getElemText(elem, 'pubDate'));
        const desc = getElemText(elem, 'description');
        const eventTimes = getElemText(elem, 'calendarEvent:EventTimes').split(' - ');
        let eventDateStr = getElemText(elem, 'calendarEvent:EventDates').trim();
        let eventDates;
        if (eventDateStr.indexOf(' - ') != -1){
            eventDates = eventDateStr.split(' - ');
        } else {
            eventDates = [eventDateStr, eventDateStr];
        }
        const startTime = parseCalendarEventDate(eventDates[0], eventTimes[0]);
        if (startTime.toString() == 'Invalid Date'){
            throw new Error('invalid date');
        }
        const endTime = parseCalendarEventDate(eventDates[1], eventTimes[1]);
        return new cls(title, pubDate, desc, startTime, endTime);
    }
}


class Feed {
    static itemClass = FeedItem;
    constructor(title, link, buildDate, description){
        this.title = title;
        this.link = link;
        this.buildDate = buildDate;
        this.description = description;
        this.itemsByStartTime = new Map();
        this.itemsById = new Map();
    }

    addChild(feedItem){
        const itemDt = feedItem.startTime;
        this.itemsById.set(feedItem.id, feedItem);

        if (!(this.itemsByStartTime.has(itemDt))){

            this.itemsByStartTime.set(itemDt, []);
        }
        const subArr = this.itemsByStartTime.get(itemDt);
        subArr.push(feedItem);
    }

    removeChild(itemId){
        if (!(this.itemsById.has(itemId))){
            throw new Error(`item "${itemId}" not in feed`);
        }
        const item = this.itemsById.get(itemId);
        const subArr = this.itemsByStartTime.get(item.startTime);
        const subIndex = subArr.indexOf(item);
        if (subIndex == -1){
            throw new Error(`item not in subArray: ${subArr}`);
        }
        delete subArr[subIndex];
        if (subArr.length == 0){
            this.itemsByStartTime.delete(item.startTime);
        }
        this.itemsById.delete(itemId);
    }

    * sortedStartTimes() {
        const dts = [...this.itemsByStartTime.keys()];
        dts.sort(function(a, b){ return a.getTime() - b.getTime() });
        yield* dts;
    }

    * sortedItems(){
        for (const dt of this.sortedStartTimes()){
            const items = this.itemsByStartTime.get(dt);
            yield* items
        }
    }

    nextItem(){
        for (const item of this.sortedItems()){
            return item;
        }
    }

    parseChild(itemEl){
        const childClass = this.constructor.itemClass;
        const child = childClass.parse(itemEl);
        if (this.itemsById.has(child.id)){
            return [false, this.itemsById.get(child.id)];
        }
        this.addChild(child);
        return [true, child];
    }

    static parse(doc){
        const cls = this;
        const elem = doc.querySelector('channel');
        const title = getElemText(elem, 'title');
        const link = getElemText(elem, 'link');
        const buildDate = parsePubDate(getElemText(elem, 'lastBuildDate'));
        const desc = getElemText(elem, 'description');
        const feed = new cls(title, link, buildDate, desc);
        
        elem.querySelectorAll('item').forEach((item) => {
            feed.parseChild(item);
        });
        return feed;
    }

    static parseFromString(docStr){
        const cls = this;
        const parser = new DOMParser();
        const doc = parser.parseFromString(docStr, 'text/xml');
        return cls.parse(doc);
    }

    static async getFeed(feedUrl){
        const cls = this;
        const xmlDoc = await fetchFeed(feedUrl);
        if (xmlDoc === null){
            return new cls('__none__', '__none__', new Date(), '__none__');
        }
        return cls.parse(xmlDoc);
    }

    update(doc){
        const elem = doc.querySelector('channel');
        const buildDate = parsePubDate(getElemText(elem, 'lastBuildDate'));
        let changed = false;

        if (buildDate > this.buildDate){
            return [changed, new Set()];
        }
        const itemsToRemove = new Set([...this.itemsById.keys()]);

        for (const childElem of elem.querySelectorAll('item')){
            let created, child;
            [created, child] = this.parseChild(childElem);
            if (created){
                changed = true;
            }
        }
        if (itemsToRemove.size){
            changed = true;
        }
        itemsToRemove.forEach((itemId) => {
            this.removeChild(itemId);
        });
        return [changed, itemsToRemove];
    }

    async fetchAndUpdate(feedUrl){
        const xmlDoc = await fetchFeed(feedUrl)
        if (xmlDoc === null){
            return false;
        }
        return this.update(xmlDoc);
    }
}


export { Feed, FeedItem, fetchFeed };
