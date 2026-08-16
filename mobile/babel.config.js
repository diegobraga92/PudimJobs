module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    // Required by react-native-reanimated v4 (moved to the worklets package).
    plugins: ['react-native-worklets/plugin'],
  };
};
