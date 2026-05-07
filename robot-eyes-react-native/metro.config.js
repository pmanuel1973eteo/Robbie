const { getDefaultConfig } = require('expo/metro-config');
const path = require('path');

const config = getDefaultConfig(__dirname);

// Mocks de módulos nativos/web que tfjs-react-native e face-landmarks-detection
// importam estaticamente mas nunca usam com runtime 'tfjs' no Expo Go.
config.resolver.extraNodeModules = {
  ...config.resolver.extraNodeModules,
  'react-native-fs':           path.resolve(__dirname, 'mocks/react-native-fs.js'),
  '@mediapipe/face_mesh':      path.resolve(__dirname, 'mocks/mediapipe.js'),
  '@mediapipe/face_detection': path.resolve(__dirname, 'mocks/mediapipe.js'),
  '@mediapipe/tasks-vision':   path.resolve(__dirname, 'mocks/mediapipe.js'),
};

module.exports = config;
