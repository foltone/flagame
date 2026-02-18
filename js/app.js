/* ============================================================
   FlaGame – Logique du jeu
   ============================================================ */

// ─── Données des drapeaux (chargées depuis drapeaux.json) ───
let FLAGS = {}; // { clé_snake: "Label original" }
let FLAG_KEYS = []; // tableau de clés

// ─── État global ───
const state = {
  mode: null,        // 'qcm' | 'input'
  rounds: 20,
  timePerQ: 20,
  currentRound: 0,
  score: 0,
  questions: [],     // tableau de clés mélangées
  history: [],       // historique des réponses pour le récap
  timerId: null,
  timeLeft: 0,
  answered: false,
};

// ─── Éléments du DOM ───
const $ = (id) => document.getElementById(id);

const screens = {
  home:       $('screen-home'),
  configQcm:  $('screen-config-qcm'),
  configInput:$('screen-config-input'),
  gameQcm:    $('screen-game-qcm'),
  gameInput:  $('screen-game-input'),
  end:        $('screen-end'),
};

// ============================================================
//  UTILITAIRES
// ============================================================

/** Affiche uniquement l'écran donné */
function showScreen(name) {
  Object.values(screens).forEach(s => s.classList.remove('active'));
  screens[name].classList.add('active');
}

/** Mélange un tableau (Fisher–Yates) */
function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/** Normalise un texte pour la comparaison (saisie libre)
 *  Retire accents, met en minuscule, retire les tirets/espaces multiples */
function normalize(str) {
  return str
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[-'']/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Compare la réponse utilisateur avec le label attendu.
 *  Tolère les accents, casse, tirets… */
function isAnswerCorrect(userAnswer, correctLabel) {
  return normalize(userAnswer) === normalize(correctLabel);
}

/** Chemin vers le SVG d'un drapeau */
function flagPath(key) {
  return `drapeau/${key}.svg`;
}

// ============================================================
//  THÈME SOMBRE / CLAIR
// ============================================================

/** Applique le thème et sauvegarde en localStorage */
function setTheme(theme) {
  document.body.classList.remove('dark', 'light');
  document.body.classList.add(theme);
  const icon = document.getElementById('theme-icon');
  if (icon) icon.textContent = theme === 'dark' ? '☀️' : '🌙';
  localStorage.setItem('flagame-theme', theme);
}

/** Charge le thème depuis localStorage ou défaut sombre */
function initTheme() {
  const saved = localStorage.getItem('flagame-theme');
  setTheme(saved || 'dark');
  const btn = document.getElementById('btn-theme');
  if (btn) {
    btn.addEventListener('click', () => {
      const current = document.body.classList.contains('dark') ? 'dark' : 'light';
      setTheme(current === 'dark' ? 'light' : 'dark');
    });
  }
}

// ============================================================
//  INIT – Chargement des données
// ============================================================

async function init() {
  // Initialiser le thème en premier (avant même le fetch)
  initTheme();

  try {
    const res = await fetch('drapeaux.json');
    FLAGS = await res.json();
    FLAG_KEYS = Object.keys(FLAGS);
    console.log(`✅ ${FLAG_KEYS.length} drapeaux chargés`);
  } catch (e) {
    console.error('Erreur chargement drapeaux.json', e);
    document.body.innerHTML = '<p style="color:red;text-align:center;padding:3rem">Erreur : impossible de charger drapeaux.json</p>';
    return;
  }

  bindEvents();
  showScreen('home');
}

// ============================================================
//  ÉVÉNEMENTS
// ============================================================

function bindEvents() {
  // ─ Accueil ─
  $('btn-mode-qcm').addEventListener('click', () => showScreen('configQcm'));
  $('btn-mode-input').addEventListener('click', () => showScreen('configInput'));

  // ─ Retour ─
  $('btn-back-qcm').addEventListener('click', () => showScreen('home'));
  $('btn-back-input').addEventListener('click', () => showScreen('home'));

  // ─ Chips de sélection ─
  initChips('chips-rounds');
  initChips('chips-time');
  initChips('chips-rounds-input');
  initChips('chips-time-input');

  // ─ Lancer QCM ─
  $('btn-start-qcm').addEventListener('click', () => {
    state.mode = 'qcm';
    state.rounds = getChipValue('chips-rounds');
    state.timePerQ = getChipValue('chips-time');
    startGame();
  });

  // ─ Lancer saisie ─
  $('btn-start-input').addEventListener('click', () => {
    state.mode = 'input';
    state.rounds = getChipValue('chips-rounds-input');
    state.timePerQ = getChipValue('chips-time-input');
    startGame();
  });

  // ─ Saisie : valider avec Enter ─
  $('input-answer').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') $('btn-validate').click();
  });

  // ─ Saisie : boutons ─
  $('btn-validate').addEventListener('click', validateInputAnswer);
  $('btn-skip').addEventListener('click', skipInputQuestion);

  // ─ Quitter la partie en cours ─
  $('btn-quit-qcm').addEventListener('click', quitGame);
  $('btn-quit-input').addEventListener('click', quitGame);

  // ─ Fin ─
  $('btn-replay').addEventListener('click', () => startGame());
  $('btn-home').addEventListener('click', () => {
    clearTimer();
    showScreen('home');
  });
}

/** Quitte la partie en cours et revient à l'accueil */
function quitGame() {
  clearTimer();
  showScreen('home');
}

/** Initialise la logique de sélection des chips */
function initChips(containerId) {
  const container = $(containerId);
  container.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      container.querySelectorAll('.chip').forEach(c => c.classList.remove('selected'));
      chip.classList.add('selected');
    });
  });
}

/** Récupère la valeur du chip sélectionné */
function getChipValue(containerId) {
  const sel = $(containerId).querySelector('.chip.selected');
  return parseInt(sel.dataset.value, 10);
}

// ============================================================
//  DÉMARRAGE DU JEU
// ============================================================

function startGame() {
  // Réinitialisation
  state.currentRound = 0;
  state.score = 0;
  state.history = [];

  // Mélanger les drapeaux et couper au nombre de manches
  const maxRounds = Math.min(state.rounds, FLAG_KEYS.length);
  state.rounds = maxRounds;
  state.questions = shuffle(FLAG_KEYS).slice(0, maxRounds);

  if (state.mode === 'qcm') {
    showScreen('gameQcm');
    nextQuestionQCM();
  } else {
    showScreen('gameInput');
    nextQuestionInput();
  }
}

// ============================================================
//  TIMER
// ============================================================

function clearTimer() {
  if (state.timerId) {
    clearInterval(state.timerId);
    state.timerId = null;
  }
}

function startTimer(timerEl, barEl, onTimeout) {
  clearTimer();
  if (state.timePerQ <= 0) {
    timerEl.textContent = '∞';
    barEl.style.width = '100%';
    return;
  }

  state.timeLeft = state.timePerQ;
  timerEl.textContent = state.timeLeft + 's';

  // Reset la barre à 100% immédiatement (sans transition)
  barEl.style.transition = 'none';
  barEl.style.width = '100%';

  // Forcer le reflow pour que le navigateur applique le 100% d'abord
  void barEl.offsetWidth;

  // Lancer la transition fluide vers 0% sur toute la durée
  barEl.style.transition = `width ${state.timePerQ}s linear`;
  barEl.style.width = '0%';

  state.timerId = setInterval(() => {
    state.timeLeft--;
    timerEl.textContent = Math.max(state.timeLeft, 0) + 's';

    if (state.timeLeft <= 0) {
      clearTimer();
      onTimeout();
    }
  }, 1000);
}

// ============================================================
//  MODE QCM
// ============================================================

function nextQuestionQCM() {
  if (state.currentRound >= state.rounds) {
    endGame();
    return;
  }

  state.answered = false;
  const key = state.questions[state.currentRound];
  const correctLabel = FLAGS[key];

  // Mise à jour HUD
  $('qcm-round').textContent = `${state.currentRound + 1} / ${state.rounds}`;
  $('qcm-score').textContent = `Score : ${state.score}`;

  // Afficher le drapeau
  const flagImg = $('qcm-flag');
  flagImg.classList.remove('show');
  setTimeout(() => {
    flagImg.src = flagPath(key);
    flagImg.alt = 'Drapeau mystère';
    flagImg.classList.add('show');
  }, 100);

  // Générer les 4 options (1 correcte + 3 aléatoires)
  const wrongKeys = FLAG_KEYS.filter(k => k !== key);
  const wrongChoices = shuffle(wrongKeys).slice(0, 3);
  const options = shuffle([key, ...wrongChoices]);

  const buttons = document.querySelectorAll('#qcm-options .option-btn');
  buttons.forEach((btn, i) => {
    const optKey = options[i];
    btn.textContent = FLAGS[optKey];
    btn.className = 'option-btn';
    btn.dataset.key = optKey;
    btn.onclick = () => handleQCMAnswer(btn, optKey, key);
  });

  // Timer
  startTimer($('qcm-timer'), $('qcm-timer-bar'), () => qcmTimeout(key));
}

function handleQCMAnswer(btn, selectedKey, correctKey) {
  if (state.answered) return;
  state.answered = true;
  clearTimer();

  const buttons = document.querySelectorAll('#qcm-options .option-btn');
  const correct = selectedKey === correctKey;

  if (correct) {
    btn.classList.add('correct');
    state.score++;
  } else {
    btn.classList.add('wrong');
    // Montrer la bonne réponse
    buttons.forEach(b => {
      if (b.dataset.key === correctKey) b.classList.add('correct');
    });
  }

  // Désactiver tous les boutons
  buttons.forEach(b => b.classList.add('disabled'));

  // Historique
  state.history.push({
    key: correctKey,
    label: FLAGS[correctKey],
    correct,
    userAnswer: FLAGS[selectedKey],
    skipped: false,
  });

  $('qcm-score').textContent = `Score : ${state.score}`;

  state.currentRound++;
  setTimeout(nextQuestionQCM, 1200);
}

function qcmTimeout(correctKey) {
  if (state.answered) return;
  state.answered = true;

  const buttons = document.querySelectorAll('#qcm-options .option-btn');
  buttons.forEach(b => {
    b.classList.add('disabled');
    if (b.dataset.key === correctKey) b.classList.add('correct');
  });

  state.history.push({
    key: correctKey,
    label: FLAGS[correctKey],
    correct: false,
    userAnswer: 'Temps écoulé',
    skipped: false,
  });

  state.currentRound++;
  setTimeout(nextQuestionQCM, 1500);
}

// ============================================================
//  MODE SAISIE LIBRE
// ============================================================

function nextQuestionInput() {
  if (state.currentRound >= state.rounds) {
    endGame();
    return;
  }

  state.answered = false;
  const key = state.questions[state.currentRound];

  // HUD
  $('input-round').textContent = `${state.currentRound + 1} / ${state.rounds}`;
  $('input-score').textContent = `Score : ${state.score}`;

  // Drapeau
  const flagImg = $('input-flag');
  flagImg.classList.remove('show');
  setTimeout(() => {
    flagImg.src = flagPath(key);
    flagImg.alt = 'Drapeau mystère';
    flagImg.classList.add('show');
  }, 100);

  // Reset input
  const input = $('input-answer');
  input.value = '';
  input.className = 'text-input';
  input.disabled = false;
  input.focus();

  // Feedback
  $('input-feedback').textContent = '';
  $('input-feedback').className = 'feedback';

  // Boutons
  $('btn-validate').disabled = false;
  $('btn-skip').disabled = false;

  // Timer
  startTimer($('input-timer'), $('input-timer-bar'), () => inputTimeout(key));
}

function validateInputAnswer() {
  if (state.answered) return;
  const key = state.questions[state.currentRound];
  const correctLabel = FLAGS[key];
  const input = $('input-answer');
  const userAnswer = input.value.trim();

  if (!userAnswer) {
    input.focus();
    return;
  }

  state.answered = true;
  clearTimer();
  input.disabled = true;
  $('btn-validate').disabled = true;
  $('btn-skip').disabled = true;

  const correct = isAnswerCorrect(userAnswer, correctLabel);
  const fb = $('input-feedback');

  if (correct) {
    state.score++;
    input.classList.add('input-correct');
    fb.textContent = '✅ Bonne réponse !';
    fb.className = 'feedback correct';
  } else {
    input.classList.add('input-wrong');
    fb.textContent = `❌ C'était : ${correctLabel}`;
    fb.className = 'feedback wrong';
  }

  state.history.push({
    key,
    label: correctLabel,
    correct,
    userAnswer,
    skipped: false,
  });

  $('input-score').textContent = `Score : ${state.score}`;
  state.currentRound++;
  setTimeout(nextQuestionInput, 1500);
}

function skipInputQuestion() {
  if (state.answered) return;
  state.answered = true;
  clearTimer();

  const key = state.questions[state.currentRound];
  const correctLabel = FLAGS[key];

  const input = $('input-answer');
  input.disabled = true;
  $('btn-validate').disabled = true;
  $('btn-skip').disabled = true;

  const fb = $('input-feedback');
  fb.textContent = `⏭️ C'était : ${correctLabel}`;
  fb.className = 'feedback wrong';

  state.history.push({
    key,
    label: correctLabel,
    correct: false,
    userAnswer: '',
    skipped: true,
  });

  state.currentRound++;
  setTimeout(nextQuestionInput, 1500);
}

function inputTimeout(key) {
  if (state.answered) return;
  state.answered = true;

  const correctLabel = FLAGS[key];
  const input = $('input-answer');
  input.disabled = true;
  $('btn-validate').disabled = true;
  $('btn-skip').disabled = true;

  const fb = $('input-feedback');
  fb.textContent = `⏰ Temps écoulé ! C'était : ${correctLabel}`;
  fb.className = 'feedback wrong';

  state.history.push({
    key,
    label: correctLabel,
    correct: false,
    userAnswer: 'Temps écoulé',
    skipped: false,
  });

  state.currentRound++;
  setTimeout(nextQuestionInput, 1500);
}

// ============================================================
//  ÉCRAN DE FIN
// ============================================================

function endGame() {
  clearTimer();
  showScreen('end');

  const score = state.score;
  const total = state.rounds;
  const pct = Math.round((score / total) * 100);

  $('end-score-value').textContent = score;
  $('end-score-total').textContent = `/ ${total}`;
  $('end-percent').textContent = `${pct}% de bonnes réponses`;

  // Message personnalisé
  let msg = '';
  if (pct === 100)      msg = '🎯 Score parfait ! Incroyable !';
  else if (pct >= 80)   msg = '🌟 Excellent ! Tu connais bien tes drapeaux !';
  else if (pct >= 60)   msg = '👍 Bien joué, continue comme ça !';
  else if (pct >= 40)   msg = '💪 Pas mal, tu progresses !';
  else                  msg = "📚 Continue à t'entraîner, tu vas t'améliorer !";
  $('end-message').textContent = msg;

  // Couleur du cercle selon le résultat
  const circle = document.querySelector('.end-score-circle');
  if (pct >= 80) {
    circle.style.borderColor = 'var(--success)';
    $('end-score-value').style.color = 'var(--success)';
  } else if (pct >= 50) {
    circle.style.borderColor = 'var(--warning)';
    $('end-score-value').style.color = 'var(--warning)';
  } else {
    circle.style.borderColor = 'var(--danger)';
    $('end-score-value').style.color = 'var(--danger)';
  }

  // Récapitulatif
  buildRecap();
}

function buildRecap() {
  const list = $('recap-list');
  list.innerHTML = '';

  state.history.forEach((item, i) => {
    const div = document.createElement('div');
    let statusClass = item.correct ? 'recap-correct' : (item.skipped ? 'recap-skipped' : 'recap-wrong');
    div.className = `recap-item ${statusClass}`;

    const icon = item.correct ? '✅' : (item.skipped ? '⏭️' : '❌');
    let detail = '';

    if (item.correct) {
      detail = 'Bonne réponse';
    } else if (item.skipped) {
      detail = 'Passé';
    } else if (item.userAnswer === 'Temps écoulé') {
      detail = 'Temps écoulé';
    } else {
      detail = `Ta réponse : ${item.userAnswer}`;
    }

    div.innerHTML = `
      <img class="recap-flag" src="${flagPath(item.key)}" alt="${item.label}">
      <div class="recap-text">
        <div class="recap-label">${item.label}</div>
        <div class="recap-detail">${detail}</div>
      </div>
      <span class="recap-icon">${icon}</span>
    `;
    list.appendChild(div);
  });
}

// ============================================================
//  LANCEMENT
// ============================================================
document.addEventListener('DOMContentLoaded', init);
