const weatherUpdateInterval = 60000;
window.stopWeather = false;


async function fetchItem(url, lastModified=null) {
    const headers = {};
    if (lastModified !== null){
        headers['If-Modified-Since'] = lastModified;
    }
    const resp = await fetch(url, { headers });
    const respModified = resp.headers.get('Last-Modified');
    if (resp.status === 304) {
        return { modified: false, data: null, lastModified: respModified };
    }
    const htmlText = await resp.text();
    const parser = new DOMParser();
    const doc = parser.parseFromString(htmlText, 'text/html');
    return { modified: true, data: doc, lastModified: respModified };
}

async function fetchWeather(lastModified=null){
    const url = document.getElementById('weather-data-url').href;
    const { modified, data, lastModified: respModified } = await fetchItem(url, lastModified);
    if (!modified) {
        return null;
    }
    return data;
}

async function fetchForecast(lastModified=null){
    const url = document.getElementById('forecast-data-url').href;
    const { modified, data, lastModified: respModified } = await fetchItem(url, lastModified);
    if (!modified) {
        return null;
    }
    return data;
}



async function updateWeather(lastModified=null){
    if (window.stopWeather){
        return false;
    }
    const scriptEl = document.getElementById('weather-json');
    const currentData = JSON.parse(scriptEl.textContent);
    const weatherDoc = await fetchWeather(lastModified);
    if (weatherDoc === null) {
        return false;
    }
    const jsonScript = weatherDoc.getElementById('weather-json');
    const weatherData = JSON.parse(jsonScript.textContent);
    jsonScript.parentElement.removeChild(jsonScript);
    if (currentData.dt === weatherData.dt){
        console.log('dts match');
        return false;
    }
    console.log('updating weather: ', weatherData);
    scriptEl.textContent = jsonScript.textContent;

    const currentDiv = document.querySelector("main > .current");
    const newElems = weatherDoc.querySelectorAll("body > *");
    currentDiv.replaceChildren(...newElems);
    showDt(currentDiv);
    return true;
}

async function updateForecast(lastModified=null){
    if (window.stopWeather){
        return false;
    }
    const scriptEl = document.getElementById('forecast-json');
    const currentData = JSON.parse(scriptEl.textContent);
    const weatherDoc = await fetchForecast(lastModified);
    if (weatherDoc === null) {
        return false;
    }
    const jsonScript = weatherDoc.getElementById('forecast-json');
    const weatherData = JSON.parse(jsonScript.textContent);
    jsonScript.parentElement.removeChild(jsonScript);
    if (currentData.dt === weatherData.dt){
        console.log('dts match');
        return false;
    }
    console.log('updating forecast: ', weatherData);
    scriptEl.textContent = jsonScript.textContent;

    const currentDiv = document.querySelector("main > .forecast");
    const newElems = weatherDoc.querySelectorAll("body > *");
    currentDiv.replaceChildren(...newElems);
    showDt(currentDiv);
    return true;
}

function showDt(elem){
    const dtFmt = new Intl.DateTimeFormat(
        'en-US',
        {
            month:'numeric',
            day:'numeric',
            hour:'2-digit',
            minute:'numeric',
        }
    );
    const p = elem.querySelector(".lastUpdate");
    const timeStamp = parseInt(p.dataset.timeStamp) * 1000;
    const dt = new Date(timeStamp);
    const td = document.querySelector(p.dataset.target);
    td.textContent = dtFmt.format(dt);
    p.parentElement.removeChild(p);
}

document.addEventListener("DOMContentLoaded", (e) => {
    document.querySelectorAll(".current, .forecast").forEach((elem) => {
        showDt(elem);
    });
});


function getNextUpdateTime(elemId){
    const scriptEl = document.getElementById(elemId);
    const data = JSON.parse(scriptEl.textContent);
    if ('next_update_iso' in data){
        return new Date(data.next_update_iso);
    }
    return null;
}


const updateFuncs = {
    weather: {
        update: updateWeather,
        getNextUpdateTime: () => getNextUpdateTime('weather-json'),
        defaultInterval: weatherUpdateInterval,
    },
    forecast: {
        update: updateForecast,
        getNextUpdateTime: () => getNextUpdateTime('forecast-json'),
        defaultInterval: weatherUpdateInterval,
    },
};

const nextUpdateTimes = {
    weather: getNextUpdateTime('weather-json'),
    forecast: getNextUpdateTime('forecast-json'),
};


function scheduleNextUpdate(key){
    const defaultInterval = updateFuncs[key].defaultInterval;
    const nextUpdateTime = nextUpdateTimes[key];
    let delayMs = defaultInterval;
    if (!(nextUpdateTime instanceof Date)){
        console.warn(`no next update time for ${key}, using default interval`);
        delayMs = defaultInterval;
    } else {
        const now = new Date();
        if (nextUpdateTime > now){
            const diffMs = nextUpdateTime - now;
            delayMs = Math.max(diffMs, 1000);
        }
    }
    console.log(`scheduling next ${key} update in ${Math.round(delayMs / 1000)} seconds`);
    window.setTimeout(() => fetchAndUpdate(key), delayMs);
}


function fetchAndUpdate(key){
    if (window.stopWeather){
        return;
    }
    const updateFunc = updateFuncs[key];
    updateFunc.update().then(
        (modified) => {
            const nextUpdateTime = updateFunc.getNextUpdateTime();
            nextUpdateTimes[key] = nextUpdateTime;
            console.log(`next ${key} update at: `, nextUpdateTime);
            scheduleNextUpdate(key);
        }
    );
}

scheduleNextUpdate('weather');
scheduleNextUpdate('forecast');
