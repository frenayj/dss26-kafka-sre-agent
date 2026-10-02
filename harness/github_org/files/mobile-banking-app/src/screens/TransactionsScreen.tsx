import React from 'react';
import {ActivityIndicator, FlatList, StyleSheet, Text, View} from 'react-native';
import {useInfiniteQuery} from '@tanstack/react-query';
import {fetchTransactions, CardTransaction} from '../api/cards';
import {signedAmount, spokenAmount} from '../utils/money';

const CREDIT_STATUSES = new Set(['REVERSED']);

function Row({tx}: {tx: CardTransaction}) {
  const isCredit = CREDIT_STATUSES.has(tx.status);
  const when = new Date(tx.authorisedAt).toLocaleString();
  return (
    <View
      style={styles.row}
      accessible
      accessibilityLabel={`${tx.merchantName}, ${spokenAmount(tx.amount, tx.currency, isCredit)}, ${when}${
        tx.status === 'PENDING' ? ', pending' : ''
      }`}>
      <View style={styles.left}>
        <Text style={styles.merchant}>{tx.merchantName}</Text>
        <Text style={styles.meta}>
          {when}
          {tx.status === 'PENDING' ? ' · Pending' : ''}
        </Text>
      </View>
      <Text style={[styles.amount, isCredit && styles.credit]}>
        {signedAmount(tx.amount, tx.currency, isCredit)}
      </Text>
    </View>
  );
}

export default function TransactionsScreen({route}: {route: {params: {cardToken: string}}}) {
  const {cardToken} = route.params;
  const query = useInfiniteQuery({
    queryKey: ['transactions', cardToken],
    queryFn: ({pageParam}) => fetchTransactions(cardToken, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: last => last.nextBefore,
  });

  if (query.isPending) {
    return <ActivityIndicator style={styles.loading} accessibilityLabel="Loading transactions" />;
  }
  if (query.isError) {
    return (
      <Text style={styles.error} accessibilityRole="alert">
        We could not load your transactions. Pull down to try again.
      </Text>
    );
  }
  return (
    <FlatList
      data={query.data.pages.flatMap(p => p.items)}
      keyExtractor={tx => tx.authId}
      renderItem={({item}) => <Row tx={item} />}
      onEndReached={() => query.hasNextPage && !query.isFetchingNextPage && query.fetchNextPage()}
      onRefresh={() => query.refetch()}
      refreshing={query.isRefetching}
      accessibilityRole="list"
    />
  );
}

const styles = StyleSheet.create({
  row: {flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 12, minHeight: 56},
  left: {flex: 1},
  merchant: {fontSize: 16, fontWeight: '600', color: '#14213D'},
  meta: {fontSize: 13, color: '#4A5568', marginTop: 2},
  amount: {fontSize: 16, fontVariant: ['tabular-nums'], color: '#14213D'},
  credit: {color: '#1B7F3B'},
  loading: {marginTop: 32},
  error: {margin: 16, color: '#B42318'},
});
