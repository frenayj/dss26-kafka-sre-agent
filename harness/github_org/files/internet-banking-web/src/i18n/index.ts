import i18n from 'i18next';
import {initReactI18next} from 'react-i18next';

const en = {
  nav: {label: 'Main', skip: 'Skip to content', transactions: 'Card transactions', statements: 'Statements', language: 'Language'},
  common: {loading: 'Loading…'},
  transactions: {
    title: 'Card transactions', caption: 'Card transactions, newest first', date: 'Date', merchant: 'Merchant',
    status: 'Status', amount: 'Amount', more: 'Show older transactions',
    error: 'We could not load your transactions. Please try again later.',
    statuses: {PENDING: 'Pending', REVERSED: 'Reversed', SETTLED: 'Completed'},
  },
  statements: {title: 'Statements', download: 'Download statement for {{period}}', error: 'Statements are unavailable right now.'},
};

const fr = {
  nav: {label: 'Principal', skip: 'Aller au contenu', transactions: 'Opérations carte', statements: 'Relevés', language: 'Langue'},
  common: {loading: 'Chargement…'},
  transactions: {
    title: 'Opérations carte', caption: 'Opérations carte, les plus récentes en premier', date: 'Date',
    merchant: 'Commerçant', status: 'Statut', amount: 'Montant', more: 'Afficher les opérations plus anciennes',
    error: 'Impossible de charger vos opérations. Veuillez réessayer plus tard.',
    statuses: {PENDING: 'En attente', REVERSED: 'Annulée', SETTLED: 'Effectuée'},
  },
  statements: {title: 'Relevés', download: 'Télécharger le relevé de {{period}}', error: 'Les relevés sont indisponibles pour le moment.'},
};

const nl = {
  nav: {label: 'Hoofdmenu', skip: 'Naar inhoud', transactions: 'Kaarttransacties', statements: 'Afschriften', language: 'Taal'},
  common: {loading: 'Laden…'},
  transactions: {
    title: 'Kaarttransacties', caption: 'Kaarttransacties, nieuwste eerst', date: 'Datum', merchant: 'Winkelier',
    status: 'Status', amount: 'Bedrag', more: 'Oudere transacties tonen',
    error: 'We konden uw transacties niet laden. Probeer het later opnieuw.',
    statuses: {PENDING: 'In behandeling', REVERSED: 'Teruggedraaid', SETTLED: 'Voltooid'},
  },
  statements: {title: 'Afschriften', download: 'Afschrift van {{period}} downloaden', error: 'Afschriften zijn nu niet beschikbaar.'},
};

const de = {
  nav: {label: 'Hauptmenü', skip: 'Zum Inhalt', transactions: 'Kartenumsätze', statements: 'Kontoauszüge', language: 'Sprache'},
  common: {loading: 'Wird geladen…'},
  transactions: {
    title: 'Kartenumsätze', caption: 'Kartenumsätze, neueste zuerst', date: 'Datum', merchant: 'Händler',
    status: 'Status', amount: 'Betrag', more: 'Ältere Umsätze anzeigen',
    error: 'Ihre Umsätze konnten nicht geladen werden. Bitte versuchen Sie es später erneut.',
    statuses: {PENDING: 'Vorgemerkt', REVERSED: 'Storniert', SETTLED: 'Gebucht'},
  },
  statements: {title: 'Kontoauszüge', download: 'Kontoauszug {{period}} herunterladen', error: 'Kontoauszüge sind derzeit nicht verfügbar.'},
};

i18n.use(initReactI18next).init({
  resources: {en: {translation: en}, fr: {translation: fr}, nl: {translation: nl}, de: {translation: de}},
  lng: navigator.language.slice(0, 2),
  fallbackLng: 'en',
  interpolation: {escapeValue: false},
});

export default i18n;
