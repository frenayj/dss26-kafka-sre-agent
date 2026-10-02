import React, {useState} from 'react';
import {Alert, StyleSheet, Switch, Text, View} from 'react-native';
import {freezeCard, unfreezeCard} from '../api/cards';

export default function CardControlsScreen({route}: {route: {params: {cardToken: string; frozen: boolean}}}) {
  const {cardToken} = route.params;
  const [frozen, setFrozen] = useState(route.params.frozen);
  const [busy, setBusy] = useState(false);

  async function toggle(next: boolean) {
    setBusy(true);
    try {
      await (next ? freezeCard(cardToken) : unfreezeCard(cardToken));
      setFrozen(next);
    } catch {
      Alert.alert('Something went wrong', 'Your card was not changed. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.container}>
      <View style={styles.row}>
        <View style={styles.text}>
          <Text style={styles.title}>Freeze card</Text>
          <Text style={styles.help}>
            Payments and cash withdrawals are declined while the card is frozen. You can unfreeze it at any time.
          </Text>
        </View>
        <Switch
          value={frozen}
          onValueChange={toggle}
          disabled={busy}
          accessibilityLabel="Freeze card"
          accessibilityHint={frozen ? 'Card is frozen. Double tap to unfreeze.' : 'Double tap to freeze your card.'}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {padding: 16},
  row: {flexDirection: 'row', alignItems: 'center', minHeight: 48},
  text: {flex: 1, paddingRight: 12},
  title: {fontSize: 16, fontWeight: '600', color: '#14213D'},
  help: {fontSize: 13, color: '#4A5568', marginTop: 4},
});
