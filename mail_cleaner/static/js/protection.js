// --- Koruma ------------------------------------------------------------------

async function toggleProtected(value, makeProtected, btn) {
  // disabled yerine aria-disabled: disabled buton odağı kaybeder, liste yeniden çizilince odak geri verilemez.
  if (btn.getAttribute('aria-disabled') === 'true') return;
  btn.setAttribute('aria-disabled', 'true');
  try {
    state.protectedList = await api('/api/protected', { value, protected: makeProtected });
    setData(state.data);
    notify(makeProtected ? `${value} korunuyor: seçilemez, taşınamaz.` : `${value} artık korunmuyor.`);
  } catch (err) {
    btn.removeAttribute('aria-disabled');
    notifyError('Koruma değiştirilemedi', err);
  }
}

