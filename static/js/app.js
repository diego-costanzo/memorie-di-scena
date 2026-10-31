/**
 * MEMORIE DI SCENA - Logica Client-Side (Vanilla JS)
 * Archivio Teatrale e Collezione di Alessio Sardelli
 * Gestione finestre modali, filtri in tempo reale, taccuino ricordi e acquisizione guidata OCR.
 * Nessuna dipendenza esterna, compatibile con tutti i browser Debian/Ubuntu.
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
});

// -----------------------------------------------------------------------------
// GESTIONE FINESTRE MODALI
// -----------------------------------------------------------------------------

function chiudiModali() {
  document.querySelectorAll('.modal-overlay').forEach((modal) => {
    modal.classList.remove('active');
  });
}

function escapeHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
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

function apriModalPrestito(elemId, titolo) {
  chiudiModali();
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

function confermaElimina(elemId, titolo) {
  chiudiModali();
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
  const query = campoRicerca ? campoRicerca.value.toLowerCase().trim() : '';
  const schede = document.querySelectorAll('.libro-card');
  let visibili = 0;

  schede.forEach((card) => {
    const cardSearchText = card.getAttribute('data-search') || '';
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

function gestisciCaricamentoFoto(files) {
  if (!files || files.length === 0) return;
  const file = files[0];

  const loading = document.getElementById('ocrLoading');
  const msgIniziale = document.getElementById('messaggioInizialeOcr');
  if (loading) loading.style.display = 'block';
  if (msgIniziale) msgIniziale.style.display = 'none';

  const formData = new FormData();
  formData.append('foto', file);

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

      if (anteprimaImg) anteprimaImg.src = dati.anteprima_url;
      if (anteprimaBox) anteprimaBox.style.display = 'block';
      if (copertinaCaricata) copertinaCaricata.value = dati.anteprima_url;

      // Renderizza righe rilevate
      const contenitore = document.getElementById('contenitoreLineeOcr');
      const sezRighe = document.getElementById('sezioneRigheOcr');
      const conteggio = document.getElementById('conteggioLinee');

      if (contenitore) contenitore.innerHTML = '';

      if (dati.linee && dati.linee.length > 0) {
        if (sezRighe) sezRighe.style.display = 'block';
        if (conteggio) conteggio.textContent = dati.linee.length + ' righe trovate';

        dati.linee.forEach((linea, index) => {
          const rowDiv = document.createElement('div');
          rowDiv.className = 'ocr-linea-item';

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

function trasferisciCampo(targetId, valore) {
  const target = document.getElementById(targetId);
  if (target) {
    target.value = valore.trim();
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

