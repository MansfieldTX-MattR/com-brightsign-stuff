async function fetchWeather(){
    const url = document.getElementById('weather-data-url').href;
    const resp = await fetch(url);
    return await resp.json();
}
async function updateWeather(){
    if (window.stopWeather){
        return;
    }
    const scriptEl = document.getElementById('weather-json');
    const currentData = JSON.parse(scriptEl.textContent);
    const weatherData = await fetchWeather();
    if (currentData.dt === weatherData.dt){
        console.log('dts match');
        return;
    }
    console.log('updating stuff: ', weatherData);
    scriptEl.textContent = JSON.stringify(weatherData);

    const currentDiv = document.querySelector("main > .current");
    currentDiv.querySelector(".temperature").textContent = `${weatherData.main.temp}°F`;
    currentDiv.querySelectorAll(".condition").forEach((el) => {
        el.remove();
    });
    weatherData.weather.forEach((w) => {
        const rootDiv = document.createElement('div');
        rootDiv.classList.add('condition');
        const img = document.createElement('img');
        img.src = w.meteocon;
        img.loading = "lazy";
        rootDiv.appendChild(img);
        const p = document.createElement('p');
        p.textContent = `(${w.description})`;
        rootDiv.appendChild(p);
        currentDiv.appendChild(rootDiv);
    });
}

function fetchAndUpdate(){
    if (window.stopWeather){
        return;
    }
    updateWeather().then(window.setTimeout(fetchAndUpdate, 10000));
}

window.setTimeout(fetchAndUpdate, 10000);