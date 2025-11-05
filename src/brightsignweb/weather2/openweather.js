const weatherUpdateInterval = 60000;
window.stopWeather = false;

let weatherModified = new Date().toUTCString();
let forecastModified = new Date().toUTCString();

async function fetchWeather(lastModified=null){
    const url = document.getElementById('weather-data-url').href;
    const headers = {'Cache-Control': 'no-cache'};
    if (lastModified !== null){
        headers['If-Modified-Since'] = lastModified;
    }
    const resp = await fetch(url, { headers });
    const respModified = resp.headers.get('Last-Modified');
    if (respModified !== null){
        weatherModified = respModified;
    }
    if (resp.status === 304) {
        return null;
    }
    const htmlText = await resp.text();
    const parser = new DOMParser();
    return parser.parseFromString(htmlText, 'text/html');
}

async function fetchForecast(lastModified=null){
    const url = document.getElementById('forecast-data-url').href;
    const headers = {'Cache-Control': 'no-cache'};
    if (lastModified !== null){
        headers['If-Modified-Since'] = lastModified;
    }
    const resp = await fetch(url, { headers });
    const respModified = resp.headers.get('Last-Modified');
    if (respModified !== null){
        forecastModified = respModified;
    }
    if (resp.status === 304) {
        return null;
    }
    const htmlText = await resp.text();
    const parser = new DOMParser();
    return parser.parseFromString(htmlText, 'text/html');
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
        return true;
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
        return true;
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


function fetchAndUpdate(){
    if (window.stopWeather){
        return;
    }
    updateWeather(weatherModified).then(
        (modified) => {
            updateForecast(forecastModified).then(
                (modified) => {
                    window.setTimeout(fetchAndUpdate, weatherUpdateInterval);
                }
            );
        }
    );
}

window.setTimeout(fetchAndUpdate, weatherUpdateInterval);
