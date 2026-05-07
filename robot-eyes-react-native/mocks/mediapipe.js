// Mock vazio para pacotes @mediapipe/* (web/WASM only)
// O face-landmarks-detection importa-os estaticamente mas nunca os usa
// quando runtime: 'tfjs' está definido.
module.exports = {
  FaceMesh: class {
    setOptions() { return Promise.resolve(); }
    onResults() {}
    send()      { return Promise.resolve(); }
    close()     {}
  },
  FaceDetection: class {
    setOptions() { return Promise.resolve(); }
    onResults() {}
    send()      { return Promise.resolve(); }
    close()     {}
  },
  FACEMESH_TESSELATION: [], FACEMESH_RIGHT_EYE: [],
  FACEMESH_LEFT_EYE: [],   FACEMESH_FACE_OVAL: [],
  FACEMESH_LIPS: [],        FACEMESH_RIGHT_IRIS: [],
  FACEMESH_LEFT_IRIS: [],   VERSION: '0.4.0',
};
