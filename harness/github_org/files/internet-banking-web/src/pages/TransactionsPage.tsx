import {useInfiniteQuery} from '@tanstack/react-query';
import {useTranslation} from 'react-i18next';
import {useSearchParams} from 'react-router-dom';
import {fetchTransactions} from '../api/http';
import {formatAmount, formatDateTime} from '../lib/format';

export default function TransactionsPage() {
  const {t, i18n} = useTranslation();
  const [params] = useSearchParams();
  const cardToken = params.get('card') ?? '';
  const query = useInfiniteQuery({
    queryKey: ['transactions', cardToken],
    queryFn: ({pageParam}) => fetchTransactions(cardToken, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: last => last.nextBefore,
    enabled: cardToken !== '',
  });

  return (
    <section aria-labelledby="tx-title">
      <h1 id="tx-title">{t('transactions.title')}</h1>
      <div aria-live="polite">
        {query.isPending && <p>{t('common.loading')}</p>}
        {query.isError && <p role="alert">{t('transactions.error')}</p>}
      </div>
      {query.data && (
        <table>
          <caption className="visually-hidden">{t('transactions.caption')}</caption>
          <thead>
            <tr>
              <th scope="col">{t('transactions.date')}</th>
              <th scope="col">{t('transactions.merchant')}</th>
              <th scope="col">{t('transactions.status')}</th>
              <th scope="col" className="num">{t('transactions.amount')}</th>
            </tr>
          </thead>
          <tbody>
            {query.data.pages.flatMap(p => p.items).map(tx => (
              <tr key={tx.authId}>
                <td>{formatDateTime(tx.authorisedAt, i18n.language)}</td>
                <td>{tx.merchantName}</td>
                <td>{t(`transactions.statuses.${tx.status}`)}</td>
                <td className="num">{formatAmount(tx.amount, tx.currency, i18n.language)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {query.hasNextPage && (
        <button type="button" onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage}>
          {t('transactions.more')}
        </button>
      )}
    </section>
  );
}
