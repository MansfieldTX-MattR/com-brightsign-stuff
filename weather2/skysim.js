import * as THREE from 'three';

import { GUI } from 'three/addons/libs/lil-gui.module.min.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { Sky } from 'three/addons/objects/Sky.js';


let camera, scene, renderer;

let sky, sun, camTrack;

let gui, effectController, effectControls;

function isTruthy(o){
    if (typeof(o) == 'string'){
        o = o.toLowerCase().trim();
        let i = null;
        try {
            i = parseInt(o);
        } catch(e){
            i = null;
        }
        if (i !== null){
            return isTruthy(i);
        }
        if (o.indexOf('true') != -1 || o.indexOf('yes') != -1){
            return true;
        }
        return false;
    }
    return Boolean(o);
}

const lat = 32.5773;
const lon = -97.1416;
const pi = Math.PI;

const queryData = new URLSearchParams(window.location.search);

const timeStep = queryData.has('timeStep') ? parseInt(queryData.get('timeStep')) : 1000;
const timeIncrement = queryData.has('timeIncrement') ? parseInt(queryData.get('timeIncrement')) : 90000;
const realTime = queryData.has('realTime') ? isTruthy(queryData.get('realTime')) : true;
const useGui = queryData.has('useGui') ? isTruthy(queryData.get('useGui')) : false;
console.log(`realTime: ${realTime}, useGui: ${useGui}`);

function getSunPos(dt){
    const data = SunCalc.getPosition(dt, lat, lon);
    return {
        elevation: THREE.MathUtils.radToDeg(data.altitude),// data.altitude * (180/pi),
        azimuth: THREE.MathUtils.radToDeg(data.azimuth),// data.azimuth * (180/pi),
    };
}


init();
render();




function initSky() {

    // Add Sky
    sky = new Sky();
    sky.scale.setScalar( 450000 );
    scene.add( sky );

    sun = new THREE.Vector3();

    /// GUI
    effectControls = {};

    effectController = {
        turbidity: .6,
        rayleigh: 1.05,
        mieCoefficient: 0.005,
        mieDirectionalG: 0.975,
        elevation: 2,
        azimuth: 180,
        exposure: renderer.toneMappingExposure,
        hour: 0,
        minute: 0,
        totalMinutes: 0,
        dt: new Date(),
    };

    effectController.hour = effectController.dt.getHours();
    effectController.minute = effectController.dt.getMinutes();
    effectController.totalMinutes = effectController.hour * 60 + effectController.minute;

    updateSunPos();
}

function trackCamera(){
    if (!camera){
        return;
    }
    const camFov = camera.fov;
    const maxXOffset = camFov / 1.75;
    const maxYOffset = camFov / 3;
    const dt = effectController.dt;
    const seconds = dt.getMinutes() * 60 + dt.getSeconds();
    const totalSeconds = dt.getHours() * 3600 + seconds;
    const oneDay = 86400;
    const noon = oneDay / 2;
    const rho = 10;
    let xOffset = 0;
    let yOffset = 0;
    let xNorm = 0;
    let yNorm = 0;
    let elevation = effectController.elevation;
    let azimuth = effectController.azimuth

    if (totalSeconds <= noon){
        yNorm = totalSeconds / noon;
        xNorm = -yNorm + 1;
        xOffset = xNorm * maxXOffset;
    } else {
        yNorm = (oneDay - totalSeconds) / noon;
        xNorm = -yNorm + 1;
        xOffset = xNorm * -maxXOffset;
    }

    yOffset = yNorm * -maxYOffset;
    elevation += yOffset;
    azimuth += xOffset;
    if (elevation < 0){
        elevation = 0;
    }

    const phi = THREE.MathUtils.degToRad(90 - elevation);
    const theta = THREE.MathUtils.degToRad(azimuth);
    camTrack.position.setFromSphericalCoords(rho, phi, theta);
    camera.lookAt(camTrack.position);
}

function updateSunPos(){
    //effectController.dt.setHours(effectController.hour);
    //console.log(effectController.dt.getHours());
    const sunPos = getSunPos(effectController.dt);
    effectController.elevation = sunPos.elevation;
    effectController.azimuth = sunPos.azimuth;
    if (effectControls.elevation === undefined){

    } else {
        //effectControls.elevation.setValue(sunPos.elevation);
        //effectControls.azimuth.setValue(sunPos.azimuth);
        effectControls.elevation.updateDisplay();
        effectControls.azimuth.updateDisplay();
        guiChanged();
    }
}

function guiChanged() {

    const uniforms = sky.material.uniforms;
    uniforms[ 'turbidity' ].value = effectController.turbidity;
    uniforms[ 'rayleigh' ].value = effectController.rayleigh;
    uniforms[ 'mieCoefficient' ].value = effectController.mieCoefficient;
    uniforms[ 'mieDirectionalG' ].value = effectController.mieDirectionalG;

    const phi = THREE.MathUtils.degToRad( 90 - effectController.elevation );
    const theta = THREE.MathUtils.degToRad( effectController.azimuth );

    sun.setFromSphericalCoords( 1, phi, theta );

    uniforms[ 'sunPosition' ].value.copy( sun );
    trackCamera();

    renderer.toneMappingExposure = effectController.exposure;
    renderer.render( scene, camera );

}

function initGui(){
    gui = new GUI();

    gui.add( effectController, 'turbidity', 0.0, 20.0, 0.1 ).onChange( guiChanged );
    gui.add( effectController, 'rayleigh', 0.0, 4, 0.001 ).onChange( guiChanged );
    gui.add( effectController, 'mieCoefficient', 0.0, 0.1, 0.001 ).onChange( guiChanged );
    gui.add( effectController, 'mieDirectionalG', 0.0, 1, 0.001 ).onChange( guiChanged );
    effectControls.elevation = gui.add( effectController, 'elevation', 0, 90, 0.1 );
    effectControls.azimuth = gui.add( effectController, 'azimuth', - 180, 180, 0.1 );
    gui.add( effectController, 'exposure', 0, 1, 0.0001 ).onChange( guiChanged );
    effectControls.hour = gui.add(effectController, 'hour', 0, 23, 1);
    effectControls.minute = gui.add(effectController, 'minute', 0, 59, 1);
    effectControls.totalMinutes = gui.add(effectController, 'totalMinutes', 0, 1339, 1);

    effectControls.elevation.onChange( guiChanged );
    effectControls.azimuth.onChange( guiChanged );

    window.gui = gui;
    window.effectController = effectController;
    window.effectControls = effectControls;

    effectControls.hour.onChange(function(){
        effectController.dt.setHours(effectController.hour);
        effectController.totalMinutes = effectController.hour * 60 + effectController.minute;
        effectControls.totalMinutes.updateDisplay();
        updateSunPos();
    });

    effectControls.minute.onChange(function(value){
        effectController.dt.setMinutes(value);
        effectController.totalMinutes = effectController.hour * 60 + effectController.minute;
        effectControls.totalMinutes.updateDisplay();
        updateSunPos();
    });

    effectControls.totalMinutes.onChange(function(value){
        const h = Math.floor(value / 60);
        const m = value % 60;
        effectController.dt.setHours(h);
        effectController.dt.setMinutes(m);
        effectController.hour = h;
        effectController.minute = m;
        effectControls.hour.updateDisplay();
        effectControls.minute.updateDisplay();
        updateSunPos();
    });


    effectController.setNow = function(){
        effectController.dt = new Date();
        effectController.hour = effectController.dt.getHours();
        effectController.minute = effectController.dt.getMinutes();
        effectController.totalMinutes = effectController.hour * 60 + effectController.minute;
        //effectControls.hour.setValue(effectController.dt.getHours());
        effectControls.hour.updateDisplay();
        effectControls.minute.updateDisplay();
        effectControls.totalMinutes.updateDisplay();
        updateSunPos();

        //const now = new Date();
        //const sunPos = getSunPos(now);
        //console.log(sunPos);
        //elevationControl.setValue(sunPos.elevation);
        //azimuthControl.setValue(sunPos.azimuth);
    };

    gui.add( effectController, 'setNow');

    guiChanged();


}

function updateFrame(){
    if (realTime){
        effectController.dt = new Date();
    } else {
        let timeStamp = effectController.dt.valueOf();
        timeStamp += timeIncrement;
        effectController.dt = new Date(timeStamp);
    }
    const infoDiv = document.getElementById('info');
    infoDiv.textContent = effectController.dt.toLocaleString();
    updateSunPos();
    guiChanged();
}

function init() {
    const canvasEl = document.getElementById('sky');

    camera = new THREE.PerspectiveCamera( 80, window.innerWidth / window.innerHeight, 100, 2000000 );

    scene = new THREE.Scene();
    camTrack = new THREE.Mesh();
    scene.add(camTrack);

    renderer = new THREE.WebGLRenderer({'canvas':canvasEl});
    renderer.setPixelRatio( window.devicePixelRatio );
    renderer.setSize( window.innerWidth, window.innerHeight );
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.5;
    //document.body.appendChild( renderer.domElement );

    initSky();
    if (useGui){
        initGui();
    } else {
        window.setInterval(updateFrame, timeStep);
    }

    window.addEventListener( 'resize', onWindowResize );

}

function onWindowResize() {

    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();

    renderer.setSize( window.innerWidth, window.innerHeight );

    render();

}

function render() {

    renderer.render( scene, camera );

}
