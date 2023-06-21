const weatherUpdateInterval = 60000;
window.stopWeather = false;

async function fetchWeather(){
    const url = document.getElementById('weather-data-url').href;
    const resp = await fetch(url);
    const htmlText = await resp.text();
    const parser = new DOMParser();
    return parser.parseFromString(htmlText, 'text/html');
}

async function fetchForecast(){
    const url = document.getElementById('forecast-data-url').href;
    const resp = await fetch(url);
    const htmlText = await resp.text();
    const parser = new DOMParser();
    return parser.parseFromString(htmlText, 'text/html');
}

async function updateWeather(){
    if (window.stopWeather){
        return;
    }
    const scriptEl = document.getElementById('weather-json');
    const currentData = JSON.parse(scriptEl.textContent);
    const weatherDoc = await fetchWeather();
    const jsonScript = weatherDoc.getElementById('weather-json');
    const weatherData = JSON.parse(jsonScript.textContent);
    jsonScript.parentElement.removeChild(jsonScript);
    if (currentData.dt === weatherData.dt){
        console.log('dts match');
        return;
    }
    console.log('updating weather: ', weatherData);
    scriptEl.textContent = jsonScript.textContent;

    const currentDiv = document.querySelector("main > .current");
    const newElems = weatherDoc.querySelectorAll("body > *");
    currentDiv.replaceChildren(...newElems);
    showDt(currentDiv);
}

async function updateForecast(){
    if (window.stopWeather){
        return;
    }
    const scriptEl = document.getElementById('forecast-json');
    const currentData = JSON.parse(scriptEl.textContent);
    const weatherDoc = await fetchForecast();
    const jsonScript = weatherDoc.getElementById('forecast-json');
    const weatherData = JSON.parse(jsonScript.textContent);
    jsonScript.parentElement.removeChild(jsonScript);
    if (currentData.dt === weatherData.dt){
        console.log('dts match');
        return;
    }
    console.log('updating forecast: ', weatherData);
    scriptEl.textContent = jsonScript.textContent;

    const currentDiv = document.querySelector("main > .forecast");
    const newElems = weatherDoc.querySelectorAll("body > *");
    currentDiv.replaceChildren(...newElems);
    showDt(currentDiv);
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
    updateWeather().then(
        updateForecast().then(
            window.setTimeout(fetchAndUpdate, weatherUpdateInterval)
        )
    );
}

window.setTimeout(fetchAndUpdate, weatherUpdateInterval);
