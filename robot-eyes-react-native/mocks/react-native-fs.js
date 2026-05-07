// Polyfill para react-native-fs usando expo-file-system
// Necessário porque @tensorflow/tfjs-react-native importa react-native-fs
// mas nós não usamos o bundle_resource_io (carregamos modelos via URL)
const FileSystem = require('expo-file-system');

module.exports = {
  readFile:   (path, encoding = 'utf8') =>
    FileSystem.readAsStringAsync(path, { encoding }),
  writeFile:  (path, data, encoding = 'utf8') =>
    FileSystem.writeAsStringAsync(path, data, { encoding }),
  exists:     (path) =>
    FileSystem.getInfoAsync(path).then(i => i.exists),
  mkdir:      (path) =>
    FileSystem.makeDirectoryAsync(path, { intermediates: true }),
  unlink:     (path) =>
    FileSystem.deleteAsync(path, { idempotent: true }),
  DocumentDirectoryPath: FileSystem.documentDirectory ?? '',
  CachesDirectoryPath:   FileSystem.cacheDirectory ?? '',
  TemporaryDirectoryPath: FileSystem.cacheDirectory ?? '',
};
