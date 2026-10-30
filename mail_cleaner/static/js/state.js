// Kategori değerleri (bulten, promosyon, ...) verinin parçası; görünen adı çeviriden gelir.
const CATEGORY_LABELS = Object.fromEntries(
  ['bulten', 'promosyon', 'bildirim', 'kisisel', 'spam'].map(category => [category, t('category.' + category)]));
const DIALOG_LIST_LIMIT = 8;
const DELETE_LABEL = t('action.trash_selected');
const UNSUB_LABEL = t('action.unsubscribe_selected');
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

