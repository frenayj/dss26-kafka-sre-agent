import {Link, Route, Routes} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import TransactionsPage from './pages/TransactionsPage';
import StatementsPage from './pages/StatementsPage';

export default function App() {
  const {t, i18n} = useTranslation();
  return (
    <>
      <a className="skip-link" href="#main">
        {t('nav.skip')}
      </a>
      <header>
        <nav aria-label={t('nav.label')}>
          <Link to="/cards/transactions">{t('nav.transactions')}</Link>
          <Link to="/cards/statements">{t('nav.statements')}</Link>
        </nav>
        <select aria-label={t('nav.language')} value={i18n.language} onChange={e => i18n.changeLanguage(e.target.value)}>
          <option value="en">English</option>
          <option value="fr">Français</option>
          <option value="nl">Nederlands</option>
          <option value="de">Deutsch</option>
        </select>
      </header>
      <main id="main">
        <Routes>
          <Route path="/cards/transactions" element={<TransactionsPage />} />
          <Route path="/cards/statements" element={<StatementsPage />} />
        </Routes>
      </main>
    </>
  );
}
