import {useQuery} from '@tanstack/react-query';
import {useTranslation} from 'react-i18next';
import {useSearchParams} from 'react-router-dom';
import {fetchStatements} from '../api/http';
import {formatAmount, formatPeriod} from '../lib/format';

/** Monthly card statements produced by card-statements-batch, served by the BFF from the document archive. */
export default function StatementsPage() {
  const {t, i18n} = useTranslation();
  const [params] = useSearchParams();
  const cardToken = params.get('card') ?? '';
  const statements = useQuery({
    queryKey: ['statements', cardToken],
    queryFn: () => fetchStatements(cardToken),
    enabled: cardToken !== '',
  });

  return (
    <section aria-labelledby="st-title">
      <h1 id="st-title">{t('statements.title')}</h1>
      {statements.isError && <p role="alert">{t('statements.error')}</p>}
      <ul>
        {statements.data?.map(s => (
          <li key={s.statementId}>
            <a href={s.downloadUrl} download aria-label={t('statements.download', {period: formatPeriod(s.statementPeriod, i18n.language)})}>
              {formatPeriod(s.statementPeriod, i18n.language)}
            </a>{' '}
            <span>{formatAmount(s.closingBalance, s.currency, i18n.language)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
