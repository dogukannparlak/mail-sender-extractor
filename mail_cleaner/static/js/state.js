const CATEGORY_LABELS = { bulten: 'Bülten', promosyon: 'Promosyon', bildirim: 'Bildirim', kisisel: 'Kişisel', spam: 'Spam' };
const DIALOG_LIST_LIMIT = 8;
const DELETE_LABEL = "Seçilenleri Çöp Kutusu'na taşı";
const UNSUB_LABEL = 'Seçilenlerin aboneliğinden çık';
// Abonelikten çıkış yalnız çıkış bağlantısı (List-Unsubscribe) okunabilen göndericilerde sunulur.
const canUnsubscribe = g => g.baglanti === true;

const state = {
  accounts: [],
  pending: [],
  sharedClient: false,
  account: null,
  data: null,
  sortMode: 'count_desc',
  scope: document.getElementById('scopeSelect')?.value || 'inbox',  // varsayılan .env'deki DEFAULT_SCOPE
  viewMode: 'address',
  categoryFilter: '',
  searchText: '',
  linkFilter: '',  // '' (tümü) | 'with' (çıkış bağlantısı olanlar) | 'without' (olmayanlar)
  protectedList: { adresler: [], alanlar: [] },
  // Seçim DOM'da değil burada tutulur; liste yeniden çizilince (sıralama, görünüm, filtre) kaybolmasın.
  selected: new Set(),
  // Tarama, taşıma, geri alma ya da abonelik işlemi sürerken işlem butonları kapalı kalır.
  busy: false,
  openPanels: new Set(),
  previewCache: new Map(),
};

const $ = id => document.getElementById(id);

