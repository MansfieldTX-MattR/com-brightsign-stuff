async function fetchWeather(){
    const url = document.getElementById('weather-data-url').href;
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
    console.log('updating stuff: ', weatherData);
    scriptEl.textContent = jsonScript.textContent;

    const currentDiv = document.querySelector("main > .current");
    const newElems = weatherDoc.querySelectorAll("body > *");
    currentDiv.replaceChildren(...newElems);
}

function fetchAndUpdate(){
    if (window.stopWeather){
        return;
    }
    updateWeather().then(window.setTimeout(fetchAndUpdate, 10000));
}

window.setTimeout(fetchAndUpdate, 10000);