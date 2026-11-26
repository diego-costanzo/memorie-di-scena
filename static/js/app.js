/**
 * MEMORIE DI SCENA - Logica Client-Side (Vanilla JS)
 * Archivio Teatrale e Collezione Personale
 * Gestione finestre modali, filtri in tempo reale, taccuino ricordi e acquisizione guidata OCR.
 * Nessuna dipendenza esterna, compatibile con tutti i browser Debian/Ubuntu.
 *
 * MAPPA DELLE SEZIONI (per chi modifica)
 * --------------------------------------
 *   Inizializzazione (DOMContentLoaded)  → ESC, overlay, ricerca live, drag&drop, conferme
 *   Utility                              → escapeHtml, csrfToken, urlSicuro
 *   Evidenziazione                       → senzaAccenti, regexAccenti, evidenzia
 *   Modali elementi                      → apriModalNuovo, apriModalModifica, apriModalPrestito...
 *   Ricerca per citazione                → eseguiRicercaCitazione (/api/ricerca_citazione)
 *   Diario dei Pensieri                  → caricaDiario, salvaNuovoPensiero, cestino, cronologia
 *   OCR                                  → gestisciCaricamentoFoto (/ocr_upload)
 *   Arresto programma                    → riponiTaccuino (/api/chiudi)
 *
 * REGOLE DI SICUREZZA
 * -------------------
 * - Ogni testo proveniente dal server va passato in `escapeHtml()` prima di
 *   finire in `innerHTML`; `evidenzia()` scappa già il testo e aggiunge <mark>.
 * - Ogni URL va passato in `urlSicuro()`: blocca javascript:, data: e i
 *   protocolli relativi.
 * - Tutte le POST devono inviare il token CSRF (campo `csrf_token` nel corpo
 *   o header `X-CSRF-Token`), altrimenti il server risponde 400.
 */

// Stato filtro tipo corrente
let filtroTipoCorrente = 'tutti';

// Inizializzazione al caricamento del DOM
document.addEventListener('DOMContentLoaded', () => {
  // Gestione chiusura modali con tasto ESC
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      chiudiModali();
    }
  });

  // Chiusura modali cliccando sull'overlay scuro
  document.querySelectorAll('.modal-overlay').forEach((overlay) => {
    overlay.addEventListener('click', function(e) {
      if (e.target === this) {
        chiudiModali();
      }
    });
  });

  // Ricerca rapida in tempo reale (se presente nella pagina)
  const campoRicerca = document.getElementById('campoRicerca');
  if (campoRicerca) {
    campoRicerca.addEventListener('input', eseguiFiltro);
  }

  // Drag & drop per acquisizione OCR (se presente nella pagina)
  const dropzone = document.getElementById('ocrDropzone');
  if (dropzone) {
    ['dragenter', 'dragover'].forEach((eventName) => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
      });
    });

    ['dragleave', 'drop'].forEach((eventName) => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
      });
    });

    dropzone.addEventListener('drop', (e) => {
      const dt = e.dataTransfer;
      if (dt && dt.files && dt.files.length > 0) {
        gestisciCaricamentoFoto(dt.files);
      }
    });
  }

  // Conferma sicura per i form che usano l'attributo data-conferma (evita
  // l'iniezione di dati utente dentro gli attributi onsubmit inline).
  document.addEventListener('submit', (e) => {
    const form = e.target;
    if (!form || !form.getAttribute) return;
    const messaggio = form.getAttribute('data-conferma');
    if (messaggio && !window.confirm(messaggio)) {
      e.preventDefault();
    }
  });
});

// -----------------------------------------------------------------------------
// GESTIONE FINESTRE MODALI
// -----------------------------------------------------------------------------

function chiudiModali() {
  document.querySelectorAll('.modal-overlay').forEach((modal) => {
    modal.classList.remove('active');
  });
  // Ripristina lo scorrimento della pagina (impostato da apriModalChiudi).
  document.body.style.overflow = '';
}

function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

function urlSicuro(url) {
  if (!url) return '#';
  const u = String(url).trim();
  // Consenti solo URL http/https o percorsi locali (es. /static/...): blocca
  // schemi pericolosi come javascript:, data:, vbscript: e i protocolli relativi.
  if (/^https?:\/\//i.test(u)) return u;
  if (u.startsWith('/') && !u.startsWith('//')) return u;
  return '#';
}

// -----------------------------------------------------------------------------
// EVIDENZIAZIONE DELLA FRASE TROVATA (insensibile ad accenti e maiuscole)
// -----------------------------------------------------------------------------
function senzaAccenti(s) {
  return String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

function regexAccenti(parola) {
  // Trasforma ogni lettera in una classe che include anche le varianti accentate:
  // così «perche» evidenzia anche «perché», aiutando chi cerca una battuta a memoria.
  const mappa = {
    a: '[aàáâäãå]', e: '[eèéêë]', i: '[iìíîï]', o: '[oòóôö]', u: '[uùúûü]', c: '[cç]'
  };
  let pattern = '';
  for (const ch of senzaAccenti(parola)) {
    const low = ch.toLowerCase();
    pattern += mappa[low] || ch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }
  return pattern;
}

function evidenzia(testo, frase) {
  if (!testo) return '';
  const raw = String(testo);
  const parole = String(frase || '')
    .split(/\s+/)
    .map((p) => p.trim())
    .filter((p) => p.length >= 2)
    .sort((a, b) => b.length - a.length);
  if (!parole.length) return escapeHtml(raw);

  // Applica il match sul testo grezzo prima dell'escape: così parole come
  // "amp" o "quot" non spezzano le entità HTML (&amp;, &quot;) e anche
  // espressioni con apostrofi vengono evidenziate senza rischi XSS.
  const patterns = parole.map(regexAccenti).filter(Boolean);
  if (!patterns.length) return escapeHtml(raw);
  const re = new RegExp('(' + patterns.join('|') + ')', 'gi');
  let out = '';
  let ultimo = 0;
  for (const m of raw.matchAll(re)) {
    if (!m[0]) continue;
    out += escapeHtml(raw.slice(ultimo, m.index));
    out += '<mark>' + escapeHtml(m[0]) + '</mark>';
    ultimo = m.index + m[0].length;
  }
  out += escapeHtml(raw.slice(ultimo));
  return out;
}

function impostaCollocazione(inputId, valore) {
  const input = document.getElementById(inputId);
  if (input) {
    input.value = valore;
    input.focus();
  }
}

// -----------------------------------------------------------------------------
// MODALE: AGGIUNGI NUOVO ELEMENTO (LIBRO / COPIONE / CD-VINILE)
// -----------------------------------------------------------------------------

function apriModalNuovo() {
  chiudiModali();
  const form = document.getElementById('formNuovoElemento');
  if (form) form.reset();
  aggiornaCampiTipoNuovo();
  const modal = document.getElementById('modalNuovo');
  if (modal) {
    modal.classList.add('active');
    setTimeout(() => {
      const inputTitolo = document.getElementById('nuovo_titolo');
      if (inputTitolo) inputTitolo.focus();
    }, 100);
  }
}

function aggiornaCampiTipoNuovo() {
  const radioChecked = document.querySelector('#modalNuovo input[name="tipo"]:checked');
  if (!radioChecked) return;
  const tipo = radioChecked.value;

  const sezCopione = document.getElementById('sezioneCopioneNuovo');
  const sezMusica = document.getElementById('sezioneMusicaNuovo');
  const labelAutore = document.getElementById('label_nuovo_autore');

  if (tipo === 'Libro') {
    if (sezCopione) sezCopione.style.display = 'none';
    if (sezMusica) sezMusica.style.display = 'none';
    if (labelAutore) labelAutore.textContent = 'Autore / Scrittore';
  } else if (tipo === 'Copione') {
    if (sezCopione) sezCopione.style.display = 'block';
    if (sezMusica) sezMusica.style.display = 'none';
    if (labelAutore) labelAutore.textContent = 'Autore del Testo Teatrale';
  } else if (tipo === 'CD / Vinile') {
    if (sezCopione) sezCopione.style.display = 'none';
    if (sezMusica) sezMusica.style.display = 'block';
    if (labelAutore) labelAutore.textContent = 'Artista / Gruppo / Cantante';
  }
}

// -----------------------------------------------------------------------------
// MODALE: REGISTRA PRESTITO
// -----------------------------------------------------------------------------

function apriModalPrestito(elemId) {
  chiudiModali();
  const card = document.querySelector('.libro-card[data-id="' + elemId + '"]');
  const titolo = card ? card.dataset.titolo : '';
  const idInput = document.getElementById('prestito_elemento_id');
  const titoloMostra = document.getElementById('prestito_titolo_mostra');
  const personaInput = document.getElementById('prestito_persona');
  const rientroInput = document.getElementById('prestito_rientro_previsto');

  if (idInput) idInput.value = elemId;
  if (titoloMostra) titoloMostra.textContent = titolo;
  if (personaInput) personaInput.value = '';
  if (rientroInput) rientroInput.value = '';

  const modal = document.getElementById('modalPrestito');
  if (modal) {
    modal.classList.add('active');
    setTimeout(() => {
      if (personaInput) personaInput.focus();
    }, 100);
  }
}

// -----------------------------------------------------------------------------
// MODALE: MODIFICA SCHEDA & TACCUINO DEI RICORDI
// -----------------------------------------------------------------------------

function apriModalModifica(elemId) {
  chiudiModali();
  fetch('/api/elementi/' + elemId + '/dettagli')
    .then((res) => res.json())
    .then((dati) => {
      if (dati.errore) {
        alert(dati.errore);
        return;
      }

      // Azzera i campi del form: senza reset un valore rimasto da una scheda
      // precedente (es. regista, formato) potrebbe essere rispedito al server
      // e contaminare i dati dell'elemento aperto.
      const formModifica = document.getElementById('formModifica');
      if (formModifica) formModifica.reset();

      document.getElementById('formModifica').action = '/api/elementi/' + elemId + '/modifica';
      document.getElementById('formAggiornaCopertina').action = '/api/elementi/' + elemId + '/aggiorna_copertina';
      document.getElementById('formAggiungiRicordo').action = '/api/elementi/' + elemId + '/appunti';

      document.getElementById('mod_titolo').value = dati.titolo || '';
      document.getElementById('mod_autore').value = dati.autore || '';
      document.getElementById('mod_collocazione').value = dati.collocazione_casa || '';
      document.getElementById('mod_note').value = dati.note || '';

      // Label autore dinamica
      const labelAutore = document.getElementById('label_mod_autore');
      if (labelAutore) {
        if (dati.tipo === 'CD / Vinile') {
          labelAutore.textContent = 'Artista / Gruppo / Cantante';
        } else if (dati.tipo === 'Copione') {
          labelAutore.textContent = 'Autore del Testo Teatrale';
        } else {
          labelAutore.textContent = 'Autore / Scrittore';
        }
      }

      // Sezione Copione
      const sezCopione = document.getElementById('sezioneCopioneModifica');
      if (dati.tipo === 'Copione') {
        if (sezCopione) sezCopione.style.display = 'block';
        document.getElementById('mod_regista').value = dati.regista || '';
        document.getElementById('mod_luogo').value = dati.prima_esibizione_luogo || '';
        document.getElementById('mod_ingaggio').value = dati.data_ingaggio || '';
        document.getElementById('mod_data_prima').value = dati.data_prima || '';
      } else {
        if (sezCopione) sezCopione.style.display = 'none';
      }

      // Sezione Musica
      const sezMusica = document.getElementById('sezioneMusicaModifica');
      if (dati.tipo === 'CD / Vinile') {
        if (sezMusica) sezMusica.style.display = 'block';
        document.getElementById('mod_etichetta_anno').value = dati.etichetta_anno || '';
        if (dati.formato === 'CD') {
          document.getElementById('mod_formato_cd').checked = true;
        } else if (dati.formato === 'Vinile 45 giri') {
          document.getElementById('mod_formato_45').checked = true;
        } else {
          document.getElementById('mod_formato_lp').checked = true;
        }
      } else {
        if (sezMusica) sezMusica.style.display = 'none';
      }

      // Riempimento Taccuino Ricordi / Appunti
      const listaRicordi = document.getElementById('listaRicordiTaccuino');
      listaRicordi.innerHTML = '';
      document.getElementById('testo_nuovo_ricordo').value = '';

      if (dati.appunti && dati.appunti.length > 0) {
        dati.appunti.forEach((appunto) => {
          const card = document.createElement('div');
          card.className = 'appunto-card';
          card.innerHTML = `
            <div class="appunto-testo">“${escapeHtml(appunto.testo)}”</div>
            <div class="appunto-meta">
              <span>📅 Annotato il ${escapeHtml(appunto.data_creazione)}</span>
              <form action="/api/appunti/${appunto.id}/elimina" method="POST" style="margin:0;" onsubmit="return confirm('Vuoi rimuovere questo appunto dal taccuino?');">
                <input type="hidden" name="csrf_token" value="${csrfToken()}">
                <button type="submit" class="btn-elimina-appunto">🗑️ Rimuovi</button>
              </form>
            </div>
          `;
          listaRicordi.appendChild(card);
        });
      } else {
        listaRicordi.innerHTML = '<p style="color: #6a492f; font-style: italic; margin-bottom: 8px;">Nessun appunto o citazione ancora annotata per questo volume. Scrivi qui sotto la prima!</p>';
      }

      // Riempimento storico prestiti
      const storicoContainer = document.getElementById('contenutoStoricoPrestiti');
      if (dati.storico_prestiti && dati.storico_prestiti.length > 0) {
        let html = '<ul style="list-style: none; padding: 0;">';
        dati.storico_prestiti.forEach((p) => {
          const statoClasse = p.stato === 'In Prestito' ? '#fff8ee; border-left: 6px solid #b86214;' : '#f4fbf5; border-left: 6px solid #237833;';
          const statoIcona = p.stato === 'In Prestito' ? '🔴 ATTUALMENTE IN PRESTITO' : '✅ Restituito';
          html += `
            <li style="background: ${statoClasse} border: 1px solid #d8c39e; border-radius: 8px; padding: 12px 16px; margin-bottom: 10px; font-size: 16px;">
              <strong>${escapeHtml(p.nome_persona)}</strong> - ${statoIcona}<br>
              <small>Prestato il: <strong>${escapeHtml(p.data_prestito)}</strong></small>
              ${p.data_rientro_effettiva ? `<br><small>Rientrato il: <strong>${escapeHtml(p.data_rientro_effettiva)}</strong></small>` : ''}
              ${p.data_rientro_prevista && p.stato === 'In Prestito' ? `<br><small>Rientro previsto: ${escapeHtml(p.data_rientro_prevista)}</small>` : ''}
            </li>
          `;
        });
        html += '</ul>';
        storicoContainer.innerHTML = html;
      } else {
        storicoContainer.innerHTML = '<p style="color: #6a492f; font-style: italic;">Nessun prestito registrato in passato.</p>';
      }

      const modal = document.getElementById('modalModifica');
      if (modal) modal.classList.add('active');
    })
    .catch((err) => {
      console.error(err);
      alert('Si è verificato un errore nel caricamento dei dati.');
    });
}

// -----------------------------------------------------------------------------
// MODALE: CONFERMA ELIMINAZIONE
// -----------------------------------------------------------------------------

function confermaElimina(elemId) {
  chiudiModali();
  const card = document.querySelector('.libro-card[data-id="' + elemId + '"]');
  const titolo = card ? card.dataset.titolo : '';
  const form = document.getElementById('formElimina');
  const titoloMostra = document.getElementById('elimina_titolo_mostra');
  if (form) form.action = '/api/elementi/' + elemId + '/elimina';
  if (titoloMostra) titoloMostra.textContent = titolo;
  const modal = document.getElementById('modalElimina');
  if (modal) modal.classList.add('active');
}

// -----------------------------------------------------------------------------
// FILTRI VELOCI E RICERCA RAPIDA ISTANTANEA
// -----------------------------------------------------------------------------

function applicaFiltroTipo(tipo, btn) {
  filtroTipoCorrente = tipo;
  document.querySelectorAll('.filter-tabs .tab-btn').forEach((b) => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  eseguiFiltro();
}

function eseguiFiltro() {
  const campoRicerca = document.getElementById('campoRicerca');
  const query = campoRicerca ? senzaAccenti(campoRicerca.value.trim()).toLowerCase() : '';
  const schede = document.querySelectorAll('.libro-card');
  let visibili = 0;

  schede.forEach((card) => {
    const cardSearchText = senzaAccenti(card.getAttribute('data-search') || '').toLowerCase();
    const cardTipo = card.getAttribute('data-tipo');
    const cardPrestito = card.getAttribute('data-prestito');

    let passaFiltroTipo = true;
    if (filtroTipoCorrente === 'Libro' && cardTipo !== 'Libro') passaFiltroTipo = false;
    if (filtroTipoCorrente === 'Copione' && cardTipo !== 'Copione') passaFiltroTipo = false;
    if (filtroTipoCorrente === 'CD / Vinile' && cardTipo !== 'CD / Vinile') passaFiltroTipo = false;
    if (filtroTipoCorrente === 'in_prestito' && cardPrestito !== '1') passaFiltroTipo = false;

    let passaRicerca = true;
    if (query.length > 0) {
      const termini = query.split(/\s+/);
      passaRicerca = termini.every((t) => cardSearchText.includes(t));
    }

    if (passaFiltroTipo && passaRicerca) {
      card.style.display = 'flex';
      visibili++;
    } else {
      card.style.display = 'none';
    }
  });

  const nessunRisultatoBox = document.getElementById('nessunRisultatoBox');
  if (nessunRisultatoBox) {
    if (visibili === 0 && schede.length > 0) {
      nessunRisultatoBox.style.display = 'block';
    } else {
      nessunRisultatoBox.style.display = 'none';
    }
  }
}

function cancellaRicerca() {
  const campoRicerca = document.getElementById('campoRicerca');
  if (campoRicerca) campoRicerca.value = '';
  filtroTipoCorrente = 'tutti';
  document.querySelectorAll('.filter-tabs .tab-btn').forEach((b) => {
    if (b.getAttribute('data-filter') === 'tutti') {
      b.classList.add('active');
    } else {
      b.classList.remove('active');
    }
  });
  eseguiFiltro();
  if (campoRicerca) campoRicerca.focus();
}

// -----------------------------------------------------------------------------
// ACQUISIZIONE GUIDATA DA FOTO (OCR)
// -----------------------------------------------------------------------------

let ocrIsbnRilevato = '';

function _etichettaRuoloOcr(ruolo) {
  const mappa = {
    titolo: '📖 Titolo suggerito',
    autore: '👤 Autore suggerito',
    regista: '🎬 Regia suggerita',
    teatro: '🏛️ Teatro',
    editore: '🏢 Editore',
    etichetta: '🎵 Etichetta / Formato',
    isbn: '🔢 Codice ISBN',
  };
  return mappa[ruolo] || '';
}

function _impostaCampoSeAutomatico(idCampo, valore) {
  const campo = document.getElementById(idCampo);
  if (!campo || !valore) return;
  // Non sovrascrive mai ciò che l'utente ha digitato o modificato a mano.
  if (!campo.value.trim() || campo.dataset.autoCompilato === '1') {
    campo.value = valore;
    campo.dataset.autoCompilato = '1';
  }
}

function svuotaCampiOcr() {
  const campi = [
    'campo_titolo', 'campo_autore', 'campo_regista', 'campo_luogo',
    'campo_ingaggio', 'campo_data_prima', 'campo_etichetta_anno', 'campo_note'
  ];
  campi.forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.value = '';
      delete el.dataset.autoCompilato;
    }
  });
  const risDiv = document.getElementById('ocrCataloghiRisultati');
  if (risDiv) {
    risDiv.innerHTML = '';
    risDiv.style.display = 'none';
  }
}

function _applicaSuggerimentiOcr(sugg) {
  if (!sugg) return;
  if (sugg.tipo) {
    const radioTipo = document.querySelector(`#formSalvaOcr input[name="tipo"][value="${sugg.tipo}"]`);
    if (radioTipo) {
      radioTipo.checked = true;
      aggiornaCampiTipoOcr();
    }
  }
  if (sugg.tipo === 'CD / Vinile' && sugg.formato) {
    const radioFmt = document.querySelector(`#formSalvaOcr input[name="formato"][value="${sugg.formato}"]`);
    if (radioFmt) radioFmt.checked = true;
  }
  _impostaCampoSeAutomatico('campo_titolo', sugg.titolo || '');
  _impostaCampoSeAutomatico('campo_autore', sugg.autore || '');
  _impostaCampoSeAutomatico('campo_regista', sugg.regista || '');
  _impostaCampoSeAutomatico('campo_luogo', sugg.prima_esibizione_luogo || '');
  _impostaCampoSeAutomatico('campo_data_prima', sugg.data_prima || '');
  _impostaCampoSeAutomatico('campo_etichetta_anno', sugg.etichetta_anno || '');
  _impostaCampoSeAutomatico('campo_note', sugg.note || '');
}

document.addEventListener('DOMContentLoaded', () => {
  const formOcr = document.getElementById('formSalvaOcr');
  if (formOcr) {
    formOcr.addEventListener('input', (e) => {
      if (e.target && e.target.dataset) {
        delete e.target.dataset.autoCompilato;
      }
    });
  }
});

function gestisciCaricamentoFoto(files) {
  if (!files || files.length === 0) return;
  const file = files[0];
  const fileInput = document.getElementById('fileFotoInput');
  if (fileInput) fileInput.value = '';

  const loading = document.getElementById('ocrLoading');
  const msgIniziale = document.getElementById('messaggioInizialeOcr');
  if (loading) loading.style.display = 'block';
  if (msgIniziale) msgIniziale.style.display = 'none';

  const formData = new FormData();
  formData.append('foto', file);
  formData.append('csrf_token', csrfToken());

  fetch('/ocr_upload', {
    method: 'POST',
    body: formData
  })
    .then((res) => res.json())
    .then((dati) => {
      if (loading) loading.style.display = 'none';

      if (!dati.success) {
        alert('Errore: ' + (dati.errore || 'Impossibile elaborare la foto.'));
        return;
      }

      // Mostra anteprima foto
      const anteprimaImg = document.getElementById('anteprimaImg');
      const anteprimaBox = document.getElementById('anteprimaBox');
      const copertinaCaricata = document.getElementById('ocr_copertina_caricata');

      if (anteprimaImg) anteprimaImg.src = urlSicuro(dati.anteprima_url);
      if (anteprimaBox) anteprimaBox.style.display = 'block';
      if (copertinaCaricata) copertinaCaricata.value = dati.anteprima_url;

      ocrIsbnRilevato = (dati.suggerimenti && dati.suggerimenti.isbn) ? dati.suggerimenti.isbn : '';

      // Avviso doppione già presente nella libreria di casa
      const boxDoppione = document.getElementById('avvisoDoppioneOcr');
      if (boxDoppione) {
        if (dati.doppione_locale && dati.doppione_locale.titolo) {
          const d = dati.doppione_locale;
          const dove = d.collocazione_casa ? ` — ${d.collocazione_casa}` : '';
          const aut = d.autore ? ` di ${d.autore}` : '';
          boxDoppione.textContent = `🏠 Sembra già nella tua libreria: «${d.titolo}»${aut}${dove}.`;
          boxDoppione.style.display = 'block';
        } else {
          boxDoppione.style.display = 'none';
          boxDoppione.textContent = '';
        }
      }

      // Renderizza righe rilevate
      const contenitore = document.getElementById('contenitoreLineeOcr');
      const sezRighe = document.getElementById('sezioneRigheOcr');
      const conteggio = document.getElementById('conteggioLinee');
      const smartBox = document.getElementById('ocrSuggerimentiBox');
      const risCataloghi = document.getElementById('ocrCataloghiRisultati');
      if (risCataloghi) {
        risCataloghi.innerHTML = '';
        risCataloghi.style.display = 'none';
      }

      if (contenitore) contenitore.innerHTML = '';

      if (dati.linee && dati.linee.length > 0) {
        if (sezRighe) sezRighe.style.display = 'block';
        if (smartBox) smartBox.style.display = 'block';
        if (conteggio) conteggio.textContent = dati.linee.length + ' righe trovate';

        // Indicazione della qualità di lettura: aiuta a capire se rifare la foto.
        const avvisoQualita = document.getElementById('avvisoQualitaOcr');
        if (avvisoQualita) {
          if (dati.qualita === 'media') {
            avvisoQualita.textContent = '👍 Lettura discreta: controlla le righe e correggi se qualcosa non torna.';
            avvisoQualita.style.display = 'block';
          } else if (dati.qualita === 'bassa') {
            avvisoQualita.textContent = '💡 La foto è poco nitida. Per un risultato migliore fotografa il frontespizio, con buona luce e senza ombre.';
            avvisoQualita.style.display = 'block';
          } else {
            avvisoQualita.textContent = '✅ Lettura nitida: il testo è stato riconosciuto con sicurezza.';
            avvisoQualita.style.display = 'block';
          }
        }

        if (dati.suggerimenti) {
          _applicaSuggerimentiOcr(dati.suggerimenti);
        }

        const ruoli = Array.isArray(dati.ruoli) ? dati.ruoli : [];
        dati.linee.forEach((linea, index) => {
          const rowDiv = document.createElement('div');
          rowDiv.className = 'ocr-linea-item';

          const ruolo = ruoli[index] || '';
          const etichettaRuolo = _etichettaRuoloOcr(ruolo);
          if (etichettaRuolo) {
            const badge = document.createElement('span');
            badge.className = `ocr-ruolo-badge ruolo-${ruolo}`;
            badge.textContent = etichettaRuolo;
            rowDiv.appendChild(badge);
          }

          const input = document.createElement('input');
          input.type = 'text';
          input.className = 'ocr-linea-input';
          input.value = linea;
          input.id = 'ocr_input_' + index;

          const btnsDiv = document.createElement('div');
          btnsDiv.className = 'ocr-pulsanti-riga';

          // Pulsante [+ Titolo]
          const btnTitolo = document.createElement('button');
          btnTitolo.type = 'button';
          btnTitolo.className = 'btn-trasferisci titolo';
          btnTitolo.innerHTML = '➕ Titolo';
          btnTitolo.onclick = () => {
            trasferisciCampo('campo_titolo', input.value);
          };

          // Pulsante [+ Autore/Artista]
          const btnAutore = document.createElement('button');
          btnAutore.type = 'button';
          btnAutore.className = 'btn-trasferisci autore';
          btnAutore.innerHTML = '➕ Autore / Artista';
          btnAutore.onclick = () => {
            trasferisciCampo('campo_autore', input.value);
          };

          // Pulsante [+ Regista]
          const btnRegista = document.createElement('button');
          btnRegista.type = 'button';
          btnRegista.className = 'btn-trasferisci regista';
          btnRegista.innerHTML = '➕ Regista';
          btnRegista.onclick = () => {
            const radioCopione = document.querySelector('input[name="tipo"][value="Copione"]');
            if (radioCopione) radioCopione.checked = true;
            aggiornaCampiTipoOcr();
            trasferisciCampo('campo_regista', input.value);
          };

          // Pulsante [+ Note]
          const btnNote = document.createElement('button');
          btnNote.type = 'button';
          btnNote.className = 'btn-trasferisci note';
          btnNote.innerHTML = '➕ Note';
          btnNote.onclick = () => {
            accodaNote(input.value);
          };

          btnsDiv.appendChild(btnTitolo);
          btnsDiv.appendChild(btnAutore);
          btnsDiv.appendChild(btnRegista);
          btnsDiv.appendChild(btnNote);

          rowDiv.appendChild(input);
          rowDiv.appendChild(btnsDiv);
          if (contenitore) contenitore.appendChild(rowDiv);
        });
      } else {
        if (sezRighe) sezRighe.style.display = 'block';
        if (smartBox) smartBox.style.display = 'none';
        if (contenitore) {
          contenitore.innerHTML = '<p style="color: #8c421d; font-size: 17px;">Nessun testo leggibile trovato nella foto. Puoi comunque compilare i campi a destra e usare la foto come copertina!</p>';
        }
      }
    })
    .catch((err) => {
      if (loading) loading.style.display = 'none';
      console.error(err);
      alert('Si è verificato un errore di connessione durante il caricamento della foto.');
    });
}

function arricchisciOcrDaCataloghi() {
  const btn = document.getElementById('btnArricchisciOcr');
  const boxRis = document.getElementById('ocrCataloghiRisultati');
  const titoloEl = document.getElementById('campo_titolo');
  const autoreEl = document.getElementById('campo_autore');
  const tipoChecked = document.querySelector('#formSalvaOcr input[name="tipo"]:checked');

  const titolo = titoloEl ? titoloEl.value.trim() : '';
  const autore = autoreEl ? autoreEl.value.trim() : '';
  const tipo = tipoChecked ? tipoChecked.value : 'Libro';

  if (!ocrIsbnRilevato && titolo.length < 3) {
    alert('Inserisci o trasferisci almeno il titolo (3 caratteri) prima di cercare nei cataloghi.');
    if (titoloEl) titoloEl.focus();
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Ricerca nei cataloghi...';
  }
  if (boxRis) {
    boxRis.innerHTML = '<div style="font-size: 14px; color: #5a3c20;">Interrogo Open Library, Google Books e MusicBrainz...</div>';
    boxRis.style.display = 'flex';
  }

  fetch('/api/ocr/arricchisci', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      isbn: ocrIsbnRilevato,
      titolo: titolo,
      autore: autore,
      tipo: tipo,
      csrf_token: csrfToken()
    })
  })
    .then((res) => res.json())
    .then((dati) => {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '🔍 Verifica e completa dai cataloghi';
      }
      if (!boxRis) return;
      if (!dati.success) {
        boxRis.innerHTML = `<div style="color: #8c2020;">${escapeHtml(dati.errore || 'Ricerca non riuscita.')}</div>`;
        return;
      }
      const risultati = dati.risultati || [];
      if (risultati.length === 0) {
        boxRis.innerHTML = '<div style="color: #6d4a2b;">Nessuna corrispondenza trovata nei cataloghi online. Puoi salvare i dati così come sono.</div>';
        return;
      }

      boxRis.innerHTML = '';
      risultati.forEach((r) => {
        const card = document.createElement('div');
        card.className = 'ocr-catalogo-card';

        const infoDiv = document.createElement('div');
        const dettagli = [r.autore, r.editore, r.anno].filter(Boolean).join(' • ');
        infoDiv.innerHTML = `<strong>${escapeHtml(r.titolo)}</strong><br><small style="color:#6d4a2b;">${escapeHtml(dettagli)} (${escapeHtml(r.fonte)})</small>`;

        const btnApplica = document.createElement('button');
        btnApplica.type = 'button';
        btnApplica.className = 'btn-trasferisci autore';
        btnApplica.textContent = '✅ Applica';
        btnApplica.addEventListener('click', () => {
          if (r.titolo) trasferisciCampo('campo_titolo', r.titolo);
          if (r.autore) trasferisciCampo('campo_autore', r.autore);
          if (tipo === 'CD / Vinile') {
            const et = [r.editore, r.anno].filter(Boolean).join(', ');
            if (et) trasferisciCampo('campo_etichetta_anno', et);
          } else {
            const extra = [r.editore ? `Editore: ${r.editore}` : '', r.anno ? `Anno: ${r.anno}` : ''].filter(Boolean).join(' • ');
            const campoNote = document.getElementById('campo_note');
            if (extra && campoNote && !campoNote.value.includes(extra)) {
              accodaNote(extra);
            }
          }
        });

        card.appendChild(infoDiv);
        card.appendChild(btnApplica);
        boxRis.appendChild(card);
      });
    })
    .catch(() => {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '🔍 Verifica e completa dai cataloghi';
      }
      if (boxRis) {
        boxRis.innerHTML = '<div style="color: #8c2020;">Connessione assente: puoi continuare a lavorare offline.</div>';
      }
    });
}

function trasferisciCampo(targetId, valore) {
  const target = document.getElementById(targetId);
  if (target) {
    target.value = valore.trim();
    delete target.dataset.autoCompilato;
    target.focus();
    target.style.transition = 'background 0.3s ease';
    target.style.background = '#fff8e3';
    setTimeout(() => {
      target.style.background = '#ffffff';
    }, 600);
  }
}

function accodaNote(valore) {
  const campo = document.getElementById('campo_note');
  if (campo) {
    delete campo.dataset.autoCompilato;
    if (campo.value.trim().length > 0) {
      campo.value = campo.value.trim() + '\n' + valore.trim();
    } else {
      campo.value = valore.trim();
    }
    campo.focus();
  }
}

function aggiornaCampiTipoOcr() {
  const radioChecked = document.querySelector('input[name="tipo"]:checked');
  if (!radioChecked) return;
  const tipo = radioChecked.value;

  const sezCopione = document.getElementById('sezioneCopioneOcr');
  const sezMusica = document.getElementById('sezioneMusicaOcr');
  const labelAutore = document.getElementById('label_autore');

  if (tipo === 'Libro') {
    if (sezCopione) sezCopione.style.display = 'none';
    if (sezMusica) sezMusica.style.display = 'none';
    if (labelAutore) labelAutore.textContent = 'Autore / Scrittore';
  } else if (tipo === 'Copione') {
    if (sezCopione) sezCopione.style.display = 'block';
    if (sezMusica) sezMusica.style.display = 'none';
    if (labelAutore) labelAutore.textContent = 'Autore del Testo Teatrale';
  } else if (tipo === 'CD / Vinile') {
    if (sezCopione) sezCopione.style.display = 'none';
    if (sezMusica) sezMusica.style.display = 'block';
    if (labelAutore) labelAutore.textContent = 'Artista / Gruppo / Cantante';
  }
}



// ==============================================================================
// GESTIONE CHIUSURA APPLICAZIONE (RIPONI IL TACCUINO)
// ==============================================================================
function apriModalChiudi() {
  chiudiModali();
  const modal = document.getElementById('modalChiudiApp');
  if (modal) {
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
}

function eseguiChiusuraApp() {
  const stato = document.getElementById('stato-chiusura');
  const azioni = document.getElementById('azioni-chiusura');
  if (stato) stato.style.display = 'block';
  if (azioni) azioni.style.display = 'none';

  fetch('/api/chiudi', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() }
  }).then(() => {
    setTimeout(() => {
      window.close();
      // Schermata di saluto rassicurante se la finestra kiosk non si chiude automaticamente da JS
      document.body.innerHTML = `
        <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; background:#1b0e07; color:#fbf5ea; font-family:'Georgia',serif; text-align:center; padding:24px;">
          <h1 style="font-size:46px; color:#dfb249; margin-bottom:18px;">🎭 Memorie di Scena</h1>
          <p style="font-size:26px; color:#ebd6b0; max-width:680px; line-height:1.5;">Il Taccuino è stato riposto con cura e il sistema è a riposo.</p>
          <p style="font-size:20px; color:#c3a88c; margin-top:24px; font-style:italic;">A presto!</p>
        </div>
      `;
    }, 400);
  }).catch(() => {
    window.close();
  });
}



// ==============================================================================
// RICERCA LIBRO PER FRASE / CITAZIONE (MULTI-DATABASE ONLINE)
// Interroga Google Books, Open Library e Internet Archive in parallelo
// ==============================================================================

function apriModalRicercaCitazione() {
  chiudiModali();
  // Reset stato precedente
  const campo = document.getElementById('campo_citazione');
  if (campo) campo.value = '';
  
  const loading = document.getElementById('citazioneLoading');
  const risultati = document.getElementById('citazioneRisultati');
  const nessuno = document.getElementById('citazioneNessunRisultato');
  
  if (loading) loading.style.display = 'none';
  if (risultati) risultati.style.display = 'none';
  if (nessuno) nessuno.style.display = 'none';
  
  const modal = document.getElementById('modalRicercaCitazione');
  if (modal) {
    modal.classList.add('active');
    setTimeout(() => {
      if (campo) campo.focus();
    }, 150);
  }
}

function eseguiRicercaCitazione() {
  const campo = document.getElementById('campo_citazione');
  const frase = campo ? campo.value.trim() : '';
  
  if (!frase || frase.length < 3) {
    alert('Scrivi almeno 3 caratteri della frase che ricordi!');
    if (campo) campo.focus();
    return;
  }
  
  const loading = document.getElementById('citazioneLoading');
  const risultatiDiv = document.getElementById('citazioneRisultati');
  const nessuno = document.getElementById('citazioneNessunRisultato');
  const lista = document.getElementById('citazioneRisultatiLista');
  
  // Mostra spinner, nascondi il resto
  if (loading) loading.style.display = 'flex';
  if (risultatiDiv) risultatiDiv.style.display = 'none';
  if (nessuno) nessuno.style.display = 'none';
  
  fetch('/api/ricerca_citazione', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ frase: frase, csrf_token: csrfToken() })
  })
  .then(res => res.json())
  .then(dati => {
    if (loading) loading.style.display = 'none';
    
    if (!dati.success) {
      alert(dati.errore || 'Si è verificato un errore nella ricerca.');
      return;
    }
    
    if (dati.risultati && dati.risultati.length > 0) {
      // Mostra i risultati
      const titolo = document.getElementById('citazioneRisultatiTitolo');
      const conteggio = document.getElementById('citazioneRisultatiConteggio');
      
      if (titolo) titolo.textContent = '📚 Libri trovati per: «' + frase + '»';
      if (conteggio) conteggio.textContent = dati.totale_risultati + ' risultat' + (dati.totale_risultati === 1 ? 'o' : 'i');
      
      if (lista) {
        lista.innerHTML = '';
        dati.risultati.forEach(r => {
          const card = document.createElement('div');
          card.className = 'citazione-risultato-card';
          
          let snippetHtml = '';
          if (r.snippet) {
            snippetHtml = `
              <div class="citazione-snippet">
                <strong>📝 Frammento di testo trovato:</strong><br>
                <em>"${evidenzia(r.snippet, frase)}"</em>
              </div>
            `;
          }
          
          let dettagliHtml = '';
          if (r.editore || r.anno || r.pagine) {
            const parti = [];
            if (r.editore) parti.push('Editore: ' + escapeHtml(r.editore));
            if (r.anno) parti.push('Anno: ' + escapeHtml(r.anno));
            if (r.pagine) parti.push(escapeHtml(r.pagine) + ' pagine');
            dettagliHtml = `<div class="citazione-dettagli">${parti.join(' • ')}</div>`;
          }
          
          let linkHtml = '';
          if (r.diario_id) {
            card.classList.add('in-diario');
            linkHtml = `<button type="button" class="citazione-link in-diario" onclick="chiudiModali(); apriPensieroDalDiario(${Number(r.diario_id)})">📜 Apri Foglio nel tuo Diario →</button>`;
          } else if (r.in_archivio) {
            card.classList.add('in-libreria');
            linkHtml = `<button type="button" class="citazione-link in-casa" onclick="chiudiModali(); apriModalModifica(${Number(r.elemento_id)})">🏠 Apri Scheda & Ricordi nella tua Collezione →</button>`;
          } else {
            if (r.link_info) {
              // urlSicuro(): accetta solo http/https o percorsi locali e blocca
              // schemi come javascript:. escapeHtml(): neutralizza le virgolette
              // nel contesto dell'attributo href.
              linkHtml = `<a href="${escapeHtml(urlSicuro(r.link_info))}" target="_blank" rel="noopener noreferrer" class="citazione-link">📖 Vedi scheda completa →</a>`;
            }
            if (r.anteprima_link) {
              linkHtml += ` <a href="${escapeHtml(urlSicuro(r.anteprima_link))}" target="_blank" rel="noopener noreferrer" class="citazione-link anteprima">👁️ Anteprima testo</a>`;
            }
          }
          
          const iconaPlaceholder = r.diario_id ? '📜' : '📖';

          card.innerHTML = `
            <div class="citazione-card-body">
              <div class="citazione-cover-box">
                ${r.copertina_url 
                  ? `<img src="${escapeHtml(urlSicuro(r.copertina_url))}" alt="Copertina" class="citazione-cover-img" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                     <div class="citazione-cover-placeholder" style="display:none;">${iconaPlaceholder}</div>`
                  : `<div class="citazione-cover-placeholder">${iconaPlaceholder}</div>`
                }
              </div>
              <div class="citazione-card-content">
                <div class="citazione-fonte-badge">${escapeHtml(r.fonte_icona || '📚')} ${escapeHtml(r.fonte || 'Database')}</div>
                <h4 class="citazione-titolo-libro">${evidenzia(r.titolo, frase)}</h4>
                <div class="citazione-autore-libro">di ${escapeHtml(r.autore)}</div>
                ${dettagliHtml}
                ${snippetHtml}
                <div class="citazione-azioni">
                  ${linkHtml}
                </div>
              </div>
            </div>
          `;
          
          lista.appendChild(card);
        });

        // Aggiorna i link di approfondimento per portali con accesso dedicato
        const qEnc = encodeURIComponent(frase.trim());
        const linkIC = document.getElementById('linkInternetCulturale');
        const linkEur = document.getElementById('linkEuropeana');
        const linkWC = document.getElementById('linkWorldCat');
        if (linkIC) linkIC.href = `https://www.internetculturale.it/it/16/search?q=${qEnc}`;
        if (linkEur) linkEur.href = `https://www.europeana.eu/it/search?query=${qEnc}`;
        if (linkWC) linkWC.href = `https://www.worldcat.org/search?q=${qEnc}`;

        const altriDiv = document.getElementById('citazioneAltriArchivi');
        if (altriDiv) altriDiv.style.display = 'block';
      }
      
      if (risultatiDiv) {
        risultatiDiv.style.display = 'block';
        setTimeout(() => {
          risultatiDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }, 50);
      }
    } else {
      // Nessun risultato
      const qEnc = encodeURIComponent(frase.trim());
      const nIC = document.getElementById('linkNessunoIC');
      const nEur = document.getElementById('linkNessunoEur');
      const nWC = document.getElementById('linkNessunoWC');
      if (nIC) nIC.href = `https://www.internetculturale.it/it/16/search?q=${qEnc}`;
      if (nEur) nEur.href = `https://www.europeana.eu/it/search?query=${qEnc}`;
      if (nWC) nWC.href = `https://www.worldcat.org/search?q=${qEnc}`;

      if (nessuno) nessuno.style.display = 'block';
    }
  })
  .catch(err => {
    if (loading) loading.style.display = 'none';
    console.error('Errore ricerca citazione:', err);
    alert('Si è verificato un errore di connessione. Verifica che Internet sia disponibile e riprova.');
  });
}

// Supporto tasto INVIO nel campo di ricerca citazione e inizializzazione Diario
document.addEventListener('DOMContentLoaded', () => {
  const campoCitazione = document.getElementById('campo_citazione');
  if (campoCitazione) {
    campoCitazione.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        eseguiRicercaCitazione();
      }
    });
  }

  // Carica i dati iniziali del Diario e aggiorna il badge di conteggio
  caricaPensieriDiario();
});

// =============================================================================
// REGISTRO 2: DIARIO DEI PENSIERI & MEMORIE (TACCUINO SU PERGAMENA)
// =============================================================================

// Stato in memoria dei pensieri attualmente visualizzati
let pensieriDiarioAttuali = [];
let timerFiltroDiario = null;

/**
 * Commuta la visualizzazione tra lo Scaffale delle Opere e il Diario dei Pensieri
 * @param {'scaffale'|'diario'} tab 
 */
function mostraRegistro(tab) {
  const tabScaffale = document.getElementById('tabRegistroScaffale');
  const tabDiario = document.getElementById('tabRegistroDiario');
  const sezScaffale = document.getElementById('sezioneScaffale');
  const sezDiario = document.getElementById('sezioneDiario');

  if (tab === 'diario') {
    if (tabScaffale) {
      tabScaffale.classList.remove('active');
      tabScaffale.setAttribute('aria-selected', 'false');
    }
    if (tabDiario) {
      tabDiario.classList.add('active');
      tabDiario.setAttribute('aria-selected', 'true');
    }
    if (sezScaffale) sezScaffale.style.display = 'none';
    if (sezDiario) sezDiario.style.display = 'block';
    
    // Ricarica la lista per assicurare freschezza
    caricaPensieriDiario();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else {
    if (tabScaffale) {
      tabScaffale.classList.add('active');
      tabScaffale.setAttribute('aria-selected', 'true');
    }
    if (tabDiario) {
      tabDiario.classList.remove('active');
      tabDiario.setAttribute('aria-selected', 'false');
    }
    if (sezScaffale) sezScaffale.style.display = 'block';
    if (sezDiario) sezDiario.style.display = 'none';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

/**
 * Carica i pensieri dal server con eventuale filtro testuale
 */
function caricaPensieriDiario(query = '', callback = null) {
  const url = query ? `/api/diario/lista?q=${encodeURIComponent(query)}` : '/api/diario/lista';

  fetch(url)
    .then(res => res.json())
    .then(dati => {
      if (!dati.success) return;

      pensieriDiarioAttuali = dati.pensieri || [];

      // Aggiorna il badge sul tab del diario
      const badge = document.getElementById('badgeConteggioDiario');
      if (badge) {
        badge.textContent = dati.totale || 0;
      }

      // Aggiorna conteggio nel pulsante cestino
      const txtCestino = document.getElementById('txtConteggioCestino');
      if (txtCestino) {
        txtCestino.textContent = dati.conteggio_cestino || 0;
      }

      const griglia = document.getElementById('grigliaPensieri');
      const boxVuoto = document.getElementById('diarioVuotoBox');
      const boxNessunFiltro = document.getElementById('diarioNessunFiltro');

      if (!griglia) return;

      if (pensieriDiarioAttuali.length === 0) {
        griglia.innerHTML = '';
        griglia.style.display = 'none';

        if (query && query.trim().length > 0) {
          if (boxNessunFiltro) boxNessunFiltro.style.display = 'block';
          if (boxVuoto) boxVuoto.style.display = 'none';
        } else {
          if (boxNessunFiltro) boxNessunFiltro.style.display = 'none';
          if (boxVuoto) boxVuoto.style.display = 'block';
        }
      } else {
        if (boxVuoto) boxVuoto.style.display = 'none';
        if (boxNessunFiltro) boxNessunFiltro.style.display = 'none';
        griglia.style.display = 'flex';

        griglia.innerHTML = '';
        pensieriDiarioAttuali.forEach(p => {
          const card = document.createElement('article');
          card.className = 'foglio-pergamena';
          card.id = `pensiero-card-${p.id}`;

          const fonteHtml = p.fonte_riferimento 
            ? `<div class="foglio-cartiglio-fonte">📖 ${escapeHtml(p.fonte_riferimento)}</div>` 
            : '';

          const titoloHtml = p.titolo 
            ? `<h3 class="foglio-titolo">${escapeHtml(p.titolo)}</h3>` 
            : '';

          const cronologiaTesto = p.num_revisioni > 0 
            ? `⏳ Cronologia (${p.num_revisioni})` 
            : '⏳ Cronologia';

          card.innerHTML = `
            <header class="foglio-pergamena-header">
              <div class="foglio-data-creazione">
                <span>🗓️</span>
                <span>${escapeHtml(p.data_creazione)}</span>
              </div>
              ${fonteHtml}
            </header>

            ${titoloHtml}

            <div class="foglio-testo-pensiero">${escapeHtml(p.testo)}</div>

            <footer class="foglio-pergamena-footer">
              <div class="foglio-azioni-sinistra">
                <button type="button" class="btn-pergamena-azione" onclick="apriModalModificaPensiero(${p.id})">
                  ✏️ Modifica
                </button>
                <button type="button" class="btn-pergamena-azione btn-pergamena-cronologia" onclick="apriModalCronologiaPensiero(${p.id})" title="Rileggi la storia delle modifiche reali nel tempo">
                  ${cronologiaTesto}
                </button>
              </div>
              <div>
                <button type="button" class="btn-pergamena-azione btn-pergamena-cestina" onclick="avviaCestinaPensiero(${p.id})" title="Sposta nel Cestino protetto (custodito per 30 giorni)">
                  🗑️ Cestina
                </button>
              </div>
            </footer>
          `;

          griglia.appendChild(card);
        });
      }

      if (typeof callback === 'function') {
        callback();
      }
    })
    .catch(err => {
      console.error('Errore caricamento pensieri diario:', err);
    });
}

/**
 * Filtro istantaneo nei pensieri del diario
 */
function filtraPensieriDiario(val) {
  const btnCancella = document.getElementById('btnCancellaDiario');
  if (btnCancella) {
    btnCancella.style.display = (val && val.trim().length > 0) ? 'inline-flex' : 'none';
  }
  clearTimeout(timerFiltroDiario);
  timerFiltroDiario = setTimeout(() => {
    caricaPensieriDiario(val ? val.trim() : '');
  }, 220);
}

/**
 * Cancella il filtro di ricerca nel diario
 */
function cancellaRicercaDiario() {
  const campo = document.getElementById('campoRicercaDiario');
  const btnCancella = document.getElementById('btnCancellaDiario');
  if (campo) {
    campo.value = '';
    campo.focus();
  }
  if (btnCancella) btnCancella.style.display = 'none';
  caricaPensieriDiario('');
}

/**
 * Apertura modale Scrivi Nuovo Pensiero
 */
function apriModalNuovoPensiero() {
  chiudiModali();
  const form = document.getElementById('formNuovoPensiero');
  if (form) form.reset();
  const modal = document.getElementById('modalNuovoPensiero');
  if (modal) {
    modal.classList.add('active');
    setTimeout(() => {
      const txt = document.getElementById('pensiero_testo');
      if (txt) txt.focus();
    }, 120);
  }
}

/**
 * Salvataggio nuovo appunto sul diario
 */
function salvaNuovoPensiero(event) {
  if (event) event.preventDefault();
  const titoloInput = document.getElementById('pensiero_titolo');
  const testoInput = document.getElementById('pensiero_testo');
  const fonteInput = document.getElementById('pensiero_fonte');

  const testo = testoInput ? testoInput.value.trim() : '';
  if (!testo) {
    alert('Scrivi il testo del pensiero o della citazione prima di custodirlo.');
    if (testoInput) testoInput.focus();
    return;
  }

  const payload = {
    titolo: titoloInput ? titoloInput.value.trim() : '',
    testo: testo,
    fonte_riferimento: fonteInput ? fonteInput.value.trim() : '',
    csrf_token: csrfToken()
  };

  fetch('/api/diario/nuovo', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  .then(res => res.json())
  .then(dati => {
    if (dati.success) {
      chiudiModali();
      if (titoloInput) titoloInput.value = '';
      if (testoInput) testoInput.value = '';
      if (fonteInput) fonteInput.value = '';
      caricaPensieriDiario();
      mostraRegistro('diario');
    } else {
      alert(dati.messaggio || 'Si è verificato un errore durante il salvataggio.');
    }
  })
  .catch(err => {
    console.error('Errore nuovo pensiero:', err);
    alert('Errore di connessione durante il salvataggio.');
  });
}

/**
 * Apertura modale Modifica Pensiero
 */
function apriModalModificaPensiero(id) {
  const p = pensieriDiarioAttuali.find(item => item.id === id);
  const idInput = document.getElementById('modifica_pensiero_id');
  const titoloInput = document.getElementById('modifica_pensiero_titolo');
  const testoInput = document.getElementById('modifica_pensiero_testo');
  const fonteInput = document.getElementById('modifica_pensiero_fonte');

  if (p) {
    if (idInput) idInput.value = p.id;
    if (titoloInput) titoloInput.value = p.titolo || '';
    if (testoInput) testoInput.value = p.testo || '';
    if (fonteInput) fonteInput.value = p.fonte_riferimento || '';
    chiudiModali();
    const modal = document.getElementById('modalModificaPensiero');
    if (modal) {
      modal.classList.add('active');
      setTimeout(() => {
        if (testoInput) testoInput.focus();
      }, 100);
    }
  } else {
    // Se non presente nella cache, carica i dettagli
    fetch(`/api/diario/${id}/cronologia`)
      .then(res => res.json())
      .then(dati => {
        if (dati.success) {
          if (idInput) idInput.value = id;
          if (titoloInput) titoloInput.value = dati.titolo || '';
          if (testoInput) testoInput.value = dati.testo_attuale || '';
          if (fonteInput) fonteInput.value = dati.fonte_riferimento || '';
          chiudiModali();
          const modal = document.getElementById('modalModificaPensiero');
          if (modal) {
            modal.classList.add('active');
            setTimeout(() => {
              if (testoInput) testoInput.focus();
            }, 100);
          }
        }
      })
      .catch(err => {
        console.error('Errore apertura modifica pensiero:', err);
        alert('Impossibile caricare il foglio del diario.');
      });
  }
}

/**
 * Invio modifiche pensiero (con salvataggio automatico versione se testo modificato)
 */
function inviaModificaPensiero(event) {
  if (event) event.preventDefault();
  const idInput = document.getElementById('modifica_pensiero_id');
  const titoloInput = document.getElementById('modifica_pensiero_titolo');
  const testoInput = document.getElementById('modifica_pensiero_testo');
  const fonteInput = document.getElementById('modifica_pensiero_fonte');

  const id = idInput ? idInput.value : null;
  const testo = testoInput ? testoInput.value.trim() : '';

  if (!id) return;
  if (!testo) {
    alert('Il testo del pensiero non può essere vuoto.');
    if (testoInput) testoInput.focus();
    return;
  }

  const payload = {
    titolo: titoloInput ? titoloInput.value.trim() : '',
    testo: testo,
    fonte_riferimento: fonteInput ? fonteInput.value.trim() : '',
    csrf_token: csrfToken()
  };

  fetch(`/api/diario/${id}/modifica`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  .then(res => res.json())
  .then(dati => {
    if (dati.success) {
      chiudiModali();
      caricaPensieriDiario();
    } else {
      alert(dati.messaggio || 'Errore durante la modifica del pensiero.');
    }
  })
  .catch(err => {
    console.error('Errore salvataggio modifica:', err);
    alert('Errore di connessione durante la modifica.');
  });
}

/**
 * Apertura cronologia fedele delle revisioni storiche
 */
function apriModalCronologiaPensiero(id) {
  chiudiModali();
  const contenitore = document.getElementById('cronologiaContenitore');
  if (contenitore) {
    contenitore.innerHTML = '<div style="text-align: center; padding: 24px; color: #5a4028; font-size: 16px;">⏳ Recupero della storia delle stesure...</div>';
  }

  const modal = document.getElementById('modalCronologiaPensiero');
  if (modal) modal.classList.add('active');

  fetch(`/api/diario/${id}/cronologia`)
    .then(res => res.json())
    .then(dati => {
      if (!dati.success || !contenitore) return;

      let html = `
        <div class="cronologia-card versione-attuale">
          <div class="cronologia-card-header">
            <span>🌟 Versione Attuale nel Diario</span>
            <span class="cronologia-badge">Attiva</span>
          </div>
          <div style="font-size: 14px; color: #43634b; margin-bottom: 8px;">
            ${dati.data_ultima_modifica ? `Ultima modifica registrata: <strong>${escapeHtml(dati.data_ultima_modifica)}</strong>` : `Creazione originale: <strong>${escapeHtml(dati.data_creazione)}</strong>`}
            ${dati.fonte_riferimento ? ` &bull; Riferimento: <em>${escapeHtml(dati.fonte_riferimento)}</em>` : ''}
          </div>
          <div class="cronologia-testo">${escapeHtml(dati.testo_attuale)}</div>
        </div>
      `;

      if (!dati.revisioni || dati.revisioni.length === 0) {
        html += `
          <div style="background: #fcf9f2; border: 1.5px dashed #d5be9b; border-radius: 8px; padding: 20px; text-align: center; color: #624323; margin-top: 16px;">
            <span style="font-size: 26px;">🪶</span><br>
            <strong style="font-size: 17px;">Prima stesura originale intatta</strong>
            <p style="margin: 6px 0 0 0; font-size: 15px; color: #7a583a;">
              Questo foglio è stato custodito il <strong>${escapeHtml(dati.data_creazione)}</strong> e non ha ancora subito modifiche successive al testo.
            </p>
          </div>
        `;
      } else {
        html += `<h4 style="margin: 20px 0 10px 0; color: #23374d; font-size: 16px; font-weight: bold;">📜 Stesure precedenti archiviate (${dati.revisioni.length}):</h4>`;
        
        // Ordina dalla più recente alla più vecchia
        const revs = [...dati.revisioni].reverse();
        revs.forEach((rev) => {
          html += `
            <div class="cronologia-card" style="margin-bottom: 12px;">
              <div class="cronologia-card-header">
                <span>⏳ Bozza del ${escapeHtml(rev.data_modifica)}</span>
                <span style="font-size: 13px; color: #627588;">Sostituita da nuova stesura</span>
              </div>
              <div class="cronologia-testo" style="color: #455668;">${escapeHtml(rev.testo_precedente)}</div>
            </div>
          `;
        });
      }

      contenitore.innerHTML = html;
    })
    .catch(err => {
      if (contenitore) {
        contenitore.innerHTML = '<div style="color: #900; padding: 20px;">Errore di caricamento della cronologia.</div>';
      }
      console.error('Errore cronologia:', err);
    });
}

/**
 * Avvia il flusso protetto di cestinamento anti-tremore (Protezione a doppio blocco)
 */
function avviaCestinaPensiero(id) {
  const p = pensieriDiarioAttuali.find(item => item.id === id);
  const estratto = p ? (p.testo.length > 95 ? p.testo.substring(0, 95) + '…' : p.testo) : '...';

  const idInput = document.getElementById('idPensieroDaCestinare');
  const anteprima = document.getElementById('testoCestinaAnteprima');
  const chk = document.getElementById('chkConfermaCestino');
  const btn = document.getElementById('btnConfermaCestina');

  if (idInput) idInput.value = id;
  if (anteprima) anteprima.textContent = '«' + estratto + '»';
  if (chk) chk.checked = false;
  if (btn) btn.disabled = true;

  chiudiModali();
  const modal = document.getElementById('modalCestinaPensiero');
  if (modal) modal.classList.add('active');
}

/**
 * Esegue lo spostamento nel cestino una volta sbloccata la spunta di sicurezza
 */
function eseguiCestinaPensiero() {
  const idInput = document.getElementById('idPensieroDaCestinare');
  const id = idInput ? idInput.value : null;
  if (!id) return;

  const btn = document.getElementById('btnConfermaCestina');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Spostamento...';
  }

  fetch(`/api/diario/${id}/cestina`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ csrf_token: csrfToken() })
  })
    .then(res => res.json())
    .then(dati => {
      if (btn) btn.textContent = '🗑️ SÌ, SPOSTA NEL CESTINO';
      if (dati.success) {
        chiudiModali();
        caricaPensieriDiario();
      } else {
        alert(dati.messaggio || 'Errore durante lo spostamento nel cestino.');
      }
    })
    .catch(err => {
      if (btn) btn.textContent = '🗑️ SÌ, SPOSTA NEL CESTINO';
      console.error('Errore cestina:', err);
      alert('Errore di connessione durante lo spostamento nel cestino.');
    });
}

/**
 * Apre il Cestino dei Ricordi con l'elenco degli appunti recuperabili entro 30 giorni
 */
function apriModalCestinoDiario() {
  chiudiModali();
  const lista = document.getElementById('listaCestino');
  if (lista) {
    lista.innerHTML = '<div style="text-align: center; padding: 24px; color: #5a4028; font-size: 16px;">⏳ Apertura del Cestino di sicurezza...</div>';
  }

  const modal = document.getElementById('modalCestinoDiario');
  if (modal) modal.classList.add('active');

  fetch('/api/diario/cestino')
    .then(res => res.json())
    .then(dati => {
      if (!dati.success || !lista) return;

      const txtConteggio = document.getElementById('txtConteggioCestino');
      if (txtConteggio) {
        txtConteggio.textContent = dati.totale || 0;
      }

      if (!dati.elementi || dati.elementi.length === 0) {
        lista.innerHTML = `
          <div style="text-align: center; padding: 40px 20px; color: #6d503b;">
            <div style="font-size: 40px; margin-bottom: 8px;">🌱</div>
            <h3 style="font-size: 20px; margin-bottom: 6px; color: #3b2210;">Il Cestino è vuoto</h3>
            <p style="font-size: 16px; margin: 0; color: #7b583f;">Tutti i tuoi pensieri e appunti sono salvi e al loro posto nel Diario.</p>
          </div>
        `;
        return;
      }

      lista.innerHTML = '';
      dati.elementi.forEach(item => {
        const card = document.createElement('div');
        card.className = 'cestino-card';

        const snippet = item.testo.length > 100 
          ? item.testo.substring(0, 100) + '…' 
          : item.testo;

        card.innerHTML = `
          <div class="cestino-info">
            <div class="cestino-titolo">${escapeHtml(item.titolo || 'Appunto senza titolo')}</div>
            <div class="cestino-testo-snippet">«${escapeHtml(snippet)}»</div>
            <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 6px;">
              <span class="cestino-badge-giorni">⏳ Custodito ancora per ${item.giorni_rimasti} giorn${item.giorni_rimasti === 1 ? 'o' : 'i'}</span>
              <span style="font-size: 13.5px; color: #7a6048;">Scritto in origine il ${escapeHtml(item.data_creazione)}</span>
            </div>
          </div>
          <div>
            <button type="button" class="btn-ripristina-rapido" onclick="ripristinaPensiero(${item.id})">
              ↩️ Ripristina nel Diario
            </button>
          </div>
        `;

        lista.appendChild(card);
      });
    })
    .catch(err => {
      if (lista) {
        lista.innerHTML = '<div style="color: #900; padding: 20px;">Errore nel caricamento del cestino.</div>';
      }
      console.error('Errore cestino:', err);
    });
}

/**
 * Ripristina un appunto dal Cestino al Diario con 1 solo clic
 */
function ripristinaPensiero(id) {
  fetch(`/api/diario/${id}/ripristina`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ csrf_token: csrfToken() })
  })
    .then(res => res.json())
    .then(dati => {
      if (dati.success) {
        apriModalCestinoDiario();
        caricaPensieriDiario();
      } else {
        alert(dati.messaggio || 'Errore durante il ripristino del pensiero.');
      }
    })
    .catch(err => {
      console.error('Errore ripristina appunto:', err);
      alert('Errore di connessione durante il ripristino.');
    });
}

/**
 * Svuota definitivamente il cestino con richiesta di conferma esplicita
 */
function confermaSvuotaCestino() {
  if (!confirm('Vuoi davvero cancellare definitivamente tutti i fogli presenti nel Cestino?\n\nQuesta operazione non potrà essere annullata.')) {
    return;
  }

  fetch('/api/diario/svuota_cestino', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ csrf_token: csrfToken() })
  })
    .then(res => res.json())
    .then(dati => {
      if (dati.success) {
        apriModalCestinoDiario();
        caricaPensieriDiario();
      } else {
        alert(dati.messaggio || 'Errore durante lo svuotamento del cestino.');
      }
    })
    .catch(err => {
      console.error('Errore svuota cestino:', err);
      alert('Errore di connessione.');
    });
}

/**
 * Navigazione dalla Bussola Culturale direttamente a un foglio del Diario
 */
function apriPensieroDalDiario(id) {
  mostraRegistro('diario');
  caricaPensieriDiario('', () => {
    setTimeout(() => {
      const card = document.getElementById(`pensiero-card-${id}`);
      if (card) {
        card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        card.classList.add('evidenzia-pulsante');
        setTimeout(() => card.classList.remove('evidenzia-pulsante'), 2500);
      }
    }, 150);
  });
}

// =============================================================================
// AGGIORNAMENTI AUTOMATICI (avviso + 1 clic)
// -----------------------------------------------------------------------------
// Il server espone /api/aggiornamenti con l'esito dell'ultimo controllo (in
// cache per 12 ore). Qui NON si aggiorna nulla da soli: si mostra un avviso.
// Il clic su «Aggiorna ora» avvia aggiorna.sh, che prima salva una copia di
// tutti i dati; la pagina attende il riavvio del server e si ricarica.
// =============================================================================

const CHIAVE_AGGIORNAMENTO_RIMANDATO = 'memorie_aggiornamento_rimandato';

function controllaAggiornamenti() {
  const banner = document.getElementById('bannerAggiornamento');
  if (!banner) return; // pagina senza avviso (es. acquisizione OCR)

  fetch('/api/aggiornamenti')
    .then((res) => res.json())
    .then((dati) => {
      if (!dati || !dati.disponibile || dati.applicazione_disattivata) return;
      // «Più tardi» vale per la sessione corrente, per non insistere.
      if (sessionStorage.getItem(CHIAVE_AGGIORNAMENTO_RIMANDATO) === String(dati.versione_remota)) return;

      const etichetta = document.getElementById('aggiornamentoVersione');
      if (etichetta) etichetta.textContent = dati.versione_remota || '';
      banner.hidden = false;

      const btnOra = document.getElementById('btnAggiornaOra');
      const btnDopo = document.getElementById('btnAggiornaDopo');
      if (btnOra) {
        btnOra.onclick = () => applicaAggiornamento(dati.versione_remota);
      }
      if (btnDopo) {
        btnDopo.onclick = () => {
          sessionStorage.setItem(CHIAVE_AGGIORNAMENTO_RIMANDATO, String(dati.versione_remota));
          banner.hidden = true;
        };
      }
    })
    .catch(() => {
      // Offline o controllo non disponibile: nessun avviso, il programma resta usabile.
    });
}

function applicaAggiornamento(versione) {
  const conferma = confirm(
    `Vuoi aggiornare Memorie di Scena alla versione ${versione || 'più recente'}?\n\n` +
    'Prima dell\'aggiornamento viene salvata automaticamente una copia di tutti i tuoi dati.\n' +
    'Il programma si chiuderà e si riaprirà da solo: non serve fare altro.'
  );
  if (!conferma) return;

  const velo = document.getElementById('veloAggiornamento');
  const testo = document.getElementById('testoAggiornamento');
  if (velo) velo.hidden = false;
  if (testo) testo.textContent = 'Preparazione dell\'aggiornamento...';

  fetch('/api/aggiornamenti/applica', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ csrf_token: csrfToken() })
  })
    .then((res) => res.json().then((dati) => ({ ok: res.ok, dati: dati })))
    .then((esito) => {
      if (!esito.ok || !esito.dati.success) {
        if (velo) velo.hidden = true;
        alert(esito.dati.errore || 'Non è stato possibile avviare l\'aggiornamento.');
        return;
      }
      attendiRiavvio(Date.now());
    })
    .catch(() => {
      if (velo) velo.hidden = true;
      alert('Errore di connessione: l\'aggiornamento non è stato avviato.');
    });
}

function attendiRiavvio(inizio) {
  const testo = document.getElementById('testoAggiornamento');
  const LIMITE_MS = 5 * 60 * 1000;

  if (Date.now() - inizio > LIMITE_MS) {
    if (testo) {
      testo.textContent = 'L\'aggiornamento sta impiegando più del previsto. Riapri il programma tra poco.';
    }
    return;
  }

  fetch('/api/aggiornamenti/stato', { cache: 'no-store' })
    .then((res) => res.json())
    .then((stato) => {
      if (stato.stato === 'ok') {
        if (testo) testo.textContent = 'Aggiornamento completato! Ricarico il programma...';
        setTimeout(() => window.location.reload(), 1200);
        return;
      }
      if (stato.stato === 'errore') {
        const velo = document.getElementById('veloAggiornamento');
        if (velo) velo.hidden = true;
        alert(stato.messaggio || 'L\'aggiornamento non è riuscito. I tuoi dati sono al sicuro.');
        return;
      }
      if (stato.stato === 'in_corso' && testo) {
        testo.textContent = stato.messaggio || 'Aggiornamento in corso...';
      }
      setTimeout(() => attendiRiavvio(inizio), 3000);
    })
    .catch(() => {
      // Il server è spento perché si sta aggiornando: è normale.
      if (testo) testo.textContent = 'Il programma si sta riavviando con la nuova versione...';
      setTimeout(() => attendiRiavvio(inizio), 3000);
    });
}

document.addEventListener('DOMContentLoaded', controllaAggiornamenti);
