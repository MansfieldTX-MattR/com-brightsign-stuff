import { Feed, FeedItem } from "./feedparser.js";

window.Feed = Feed;

const feedUrlElem = document.getElementById('feed-url');
const params = new URLSearchParams(window.location.search);
if (params.has('feedUrl')){
    feedUrlElem.href = decodeURIComponent(params.get('feedUrl'));
}
const showDescriptions = params.has('showDescriptions');
const maxItems = params.has('maxItems') ? parseInt(params.get('maxItems')) : null;
const feedUrl = new URL(feedUrlElem.href);
const updateInterval = 60;

if (window.location.host == 'localhost:8080'){
    feedUrl.host = 'localhost:8080';
}

class Logger {
    constructor (){
        this.logDiv = document.querySelector(".message-log");
        console.oldLog = console.log;
        const self = this;
        console.log = function(){
            const args = [...arguments];
            self.log.apply(self, args);
            console.oldLog.apply(undefined, args);
        };
    }

    log(){
        const args = [...arguments];
        const msg = this.processMsg(args);
        this.appendLog(msg);
    }

    error(e){
        const msg = this.processMsg([e]);
        this.appendLog(msg);
        console.error(e);
    }

    appendLog(msg){
        const p = document.createElement('p');
        p.textContent = msg;
        this.logDiv.prepend(p);
    }
    processMsg(argList){
        let output = '';
        for (const arg of argList){
            if (arg instanceof Error){
                output += arg.name + ': ' + arg.message;
            }
            if (
                typeof arg === "object" &&
                typeof JSON === "object" &&
                typeof JSON.stringify === "function"
            ) {
                output += JSON.stringify(arg);   
            } else {
                output += arg;   
            }
            output += ' ';
        };
        return output;
    }
}

const logger = new Logger();
window.logger = logger;


const dateFmt = new Intl.DateTimeFormat(
    'en-US',
    {
        year:'numeric',
        month:'short',
        day:'numeric',
        weekday:'short',
        
    }
);
const timeFmt = new Intl.DateTimeFormat(
    'en-US',
    {
        hour:'numeric',
        minute:'numeric',
    }
);


class MeetingItem extends FeedItem {
    constructor(...args){
        super(...args);
        this.html = null;
    }
    buildHtml(){
        if (this.html === null){
            this.html = this.createHtml(true);
        }
        return this.html;
    }

    createHtml(){
        /*
        <article class="feed-list-item" id="{{ item.id }}">
            <h2>{{ item.title }}</h2>
            {% if showDescriptions %}
            <section class="item-description">
                <dl>
                {% for descItem in descriptionLines %}
                    <dt>{{ descItem.title }}</dt>
                    <dd>{{ descItem.body }}</dd>
                {% endfor %}
                </dl>
            {% else %}
            <section class="item-date-times">
                <div class="item-date">{{ itemDate }}</div>
                <div class="item-time">{{ itemTime }}</div>
            </section>
            {% endif %}
        </article>
        */
        const rootEl = document.createElement('article');
        rootEl.id = this.id;
        rootEl.classList.add('feed-list-item');
        if (maxItems !== null){
            rootEl.style.maxHeight = `calc(98vh / ${maxItems}`;
        }
        const startDateStr = dateFmt.format(this.startTime);
        const startTimeStr = timeFmt.format(this.startTime);
        const endTimeStr = timeFmt.format(this.endTime);
        rootEl.dataset.itemId = this.id;
        rootEl.dataset.startDate = startDateStr;
        rootEl.dataset.startTime = startTimeStr;

        const headerEl = document.createElement('h2');
        headerEl.textContent = this.title;
        rootEl.appendChild(headerEl);
        if (!showDescriptions){
            const dateEl = document.createElement('section');
            dateEl.classList.add('item-date-times');
            const p1 = document.createElement('div');
            p1.classList.add('item-date');
            p1.textContent = startDateStr;
            dateEl.appendChild(p1);
            const p2 = document.createElement('div');
            p2.classList.add('item-time');
            p2.textContent = [startTimeStr, endTimeStr].join(' to ');
            dateEl.appendChild(p2);
            rootEl.appendChild(dateEl);
        } else {
            const descEl = document.createElement('section');
            descEl.classList.add('item-description')
            const parser = new DOMParser();
            const doc = parser.parseFromString(this.description, 'text/html');
            let nodes = [];
            let curParent = null;
            // let curElem = null;
            let needBr = false;
            let realDescNodes = [];

            doc.querySelector('body').childNodes.forEach((node) => {
                let realNode = null;
                if (node.nodeName == '#text'){
                    if (node.textContent.trim().length == 0){
                        realNode = null;
                    } else if (needBr){
                        realNode = document.createElement('p');
                        needBr = false;
                        realNode.textContent = node.textContent;
                    } else {
                        realNode = document.createElement('span');
                        realNode.textContent = node.textContent;
                    }

                } else if (node.nodeName == 'STRONG'){
                    if (curParent !== null){
                        nodes.push(curParent);
                    }
                    realNode = document.createElement('dt');
                    realNode.textContent = node.textContent;
                    curParent = document.createElement('dd');
                    if (node.textContent == 'Description:'){
                        realDescNodes.push(realNode);
                        realDescNodes.push(curParent);
                    } else {
                        nodes.push(realNode);
                        nodes.push(curParent);
                    }
                    realNode = null;
                } else if (node.nodeName == 'BR'){
                    needBr = true;
                    realNode = null;
                }
                if (realNode !== null){
                    curParent.append(realNode);
                }
            });
            const dl = document.createElement('dl');
            dl.append(...realDescNodes);
            dl.append(...nodes);
            descEl.appendChild(dl);
            rootEl.appendChild(descEl);
        }
        return rootEl;
    }
}

class MeetingFeed extends Feed {
    static itemClass = MeetingItem;

    * sortedHtmlElems(){
        let i = 0;
        for (const item of this.sortedItems()){
            if (maxItems !== null && i >= maxItems){
                break;
            }
            yield item.buildHtml();
            i += 1;
        }
    }
}


const listEl = document.querySelector("#main .item-container");

async function buildFeed(){
    const feedObj = await MeetingFeed.getFeed(feedUrl);
    if (feedObj.title == '__none__'){
        return null;
    }
    const elems = [...feedObj.sortedHtmlElems()];
    listEl.append(...elems);
    return feedObj;
}

async function updateFeed(feedObj){
    let changed, itemsToRemove;
    [changed, itemsToRemove] = await feedObj.fetchAndUpdate(feedUrl);
    if (!changed){
        return;
    }
    while (listEl.firstChild){
        listEl.removeChild(listEl.firstChild);
    }

    const elems = [...feedObj.sortedHtmlElems()];
    listEl.append(...elems);
}

async function buildAndUpdate(){
    let feedObj = null;

    function waitForTimer(){
        return new Promise(resolve => {
            setTimeout(() => {
                resolve('resolved');
            }, updateInterval * 1000);
        });
    }
    // feedObj = await buildFeed();
    // return;

    while(!(window.stopUpdating)){
        try {
            if (feedObj === null){
                console.log('building feed');
                feedObj = await buildFeed();
            } else {
                console.log('updating feed');
                await updateFeed(feedObj);
            }

        } catch(e) {
            logger.error(e);
        } finally {
            await waitForTimer();
        }
    }
}

buildAndUpdate();

