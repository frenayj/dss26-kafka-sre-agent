import * as Keychain from 'react-native-keychain';

const SERVICE = 'bank.dss26.session';

/**
 * The refresh token lives in the Keychain/Keystore behind biometrics; it is
 * read only when the user unlocks the app with Face ID, Touch ID or the
 * device fingerprint.
 */
export async function storeRefreshToken(token: string): Promise<void> {
  await Keychain.setGenericPassword('refresh', token, {
    service: SERVICE,
    accessControl: Keychain.ACCESS_CONTROL.BIOMETRY_CURRENT_SET,
    accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
}

export async function unlockRefreshToken(prompt: string): Promise<string | null> {
  const creds = await Keychain.getGenericPassword({
    service: SERVICE,
    authenticationPrompt: {title: prompt},
  });
  return creds ? creds.password : null;
}

export async function clearSession(): Promise<void> {
  await Keychain.resetGenericPassword({service: SERVICE});
}
