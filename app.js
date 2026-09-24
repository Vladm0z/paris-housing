/* Student Paris Map - cafeterias, apartments, amenities */
const CONFIG = {
	darkGreenMin: 120, greenMin: 60, opensSoonMin: 60,
	refreshSec: 60, center: [48.8566, 2.3522], zoom: 12,
	groupDecimals: 5, // ~1 m: venues closer than this merge into one marker
	staleHours: 96,
};

const COLORS = { dark_green:'#006400', green:'#00a650', yellow:'#ffd400',
				 red:'#e53935', blue:'#1e88e5', unknown:'#8d8d8d', confirmed:'#424242' };
const COLOR_KEY = Object.fromEntries(Object.entries(COLORS).map(([k, v]) => [v, k]));

/* Amenity category colors */
const AMENITY_COLORS = {
	hypermarket: '#6a1b9a', supermarket: '#8e24aa', discount: '#ab47bc',
	convenience: '#ce93d8', organic: '#43a047', zero_waste: '#66bb6a',
	bakery: '#f9a825', butcher: '#d84315', cheese: '#ff8f00',
	greengrocer: '#7cb342', seafood: '#0288d1', health_food: '#26a69a',
	pharmacy: '#00897b', laundry: '#546e7a',
};

/* DPE energy class colors (French diagnostic) */
const DPE_COLORS = { A:'#00a651', B:'#51b848', C:'#cdd542', D:'#f6eb15',
										 E:'#f5c50f', F:'#f0932b', G:'#eb1c24' };

const WD = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
const WD_SHORT = { Mon:0, Tue:1, Wed:2, Thu:3, Fri:4, Sat:5, Sun:6 };
const RANK = { open: 4, opens_soon: 3, closed: 2, confirmed: 1, unknown: 0 };

/* university filter table: id, label, pattern tested against (access note + venue name) */
const UNIS = [
	['sorbonne', 'Sorbonne Université', /sorbonne\s+universit/],
	['paris1', 'Université Paris 1 Panthéon-Sorbonne', /panth[ée]on\s*-?\s*sorbonne|paris\s*[1i]\b[^,;]*sorbonne/],
	['assas', 'Université Panthéon-Assas (Paris II)', /assas/],
	['cite', 'Université Paris Cité', /universit[ée]\s+de\s+paris\b/],
	['dauphine', 'Université Paris Dauphine-PSL', /dauphine/],
	['sciencespo', 'Sciences Po', /sciences\s*po/],
	['inalco', 'INALCO', /inalco/],
	['ens', 'ENS (École normale supérieure)', /\bens\b|ens\s+jourdan/],
	['ensa', 'ENSA Paris-Belleville', /\bensa\b/],
	['icp', 'Institut Catholique de Paris', /institut\s+catholique/],
	['mines', 'Mines Paris-PSL', /mines/],
	['nation', 'Campus Nation', /campus\s+nation/],
	['condorcet', 'Campus Condorcet', /campus\s+condorcet/],
];
const GENERIC_STAFF_RE = /tout\s+(le\s+)?personnel|personnels?\s+de\s+l['']enseignement/;
const profile = { uni: null, staff: false };

/* Layer state */
const layers = {
	cafeterias: { visible: true, items: [], count: 0 },
	apartments: { visible: true, markers: [], count: 0, filtered: 0, blurDisk: null },
	amenities:	{ visible: true, markers: [], count: 0 },
};

/* Amenity sub-category visibility */
const amenityVisible = {};

/* Apartment filter state */
const aptFilter = {
	priceMin: 0, priceMax: 5000,
	surfaceMin: 0, roomsMin: 0,
	energyClass: '',
	onlyMultiSource: false,
};

/* curated official campus/access maps: [pattern, label, url] */
const CAMPUS_MAPS = [
	[/jussieu|cuvier|atrium|l'express|l'ardoise/,
	 'Campus Jussieu plan', 'https://sciences.sorbonne-universite.fr/vie-de-campus-sciences/accueil-vie-pratique/plan-du-campus'],
	[/clignancourt|francis de croisset|malesherbes|18 bis rue de la sorbonne/,
	 'Sorbonne campuses card', 'https://guideetudiant.sorbonne-universite.fr/universite/carte-des-campus'],
	[/cit[ée] internationale|23 boulevard jourdan/,
	 'Cité U campus plan', 'https://www.ciup.fr/wp-content/uploads/2023/07/PLAN-2023.pdf'],
	[/48 boulevard jourdan|ens jourdan/,
	 'Campus Jourdan access', 'https://www.parisschoolofeconomics.eu/en/about-pse/access-jourdan-campus/'],
	[/saint-guillaume|saint-thomas|sciences\s*po/,
	 'Sciences Po campus plan', 'https://www.sciencespo.fr/sites/default/files/Plan-SciencesPo.pdf'],
	[/inalco/,
	 'INALCO orientation', 'https://www.inalco.fr/sorienter'],
	[/institut catholique|21 rue d'assas/,
	 'ICP campus plan', 'https://www.icp.fr/vie-du-campus/paris/plan-du-campus-de-paris'],
	[/porte de la chapelle|condorcet/,
	 'Campus Condorcet Paris', 'https://www.campus-condorcet.fr/fr/le-campus/site-de-paris'],
	[/universit[ée] de paris|iut de paris|lacretelle|necker|pharmacie|saints-p|bichat|pajol|mazet|observatoire/,
	 'Paris Cité sites', 'https://u-paris.fr/nos-sites-et-campus/'],
];

/* CROUS venue pages contain hours/access info, but NOT menus.
	 Menus are injected via p.menu_refs from the CROUStillant API. */
const VENUE_PAGES = [
	[/cuvier|ru cuvier/, 'RU Cuvier venue page', 'https://www.crous-paris.fr/restaurant/ru-cuvier-3/'],
	[/l'express|lexpress/, "L'Express venue page", 'https://www.crous-paris.fr/restaurant/lexpress/'],
	[/l'ardoise|brasserie l'ardoise/, "Brasserie l'Ardoise venue page", 'https://www.crous-paris.fr/restaurant/brasserie-lardoise-3/'],
	[/l'atrium|cafeteria l'atrium/, "Cafétéria l'Atrium venue page", 'https://www.crous-paris.fr/restaurant/cafeteria-latrium-3/'],
	[/saint-guillaume|saint guillaume/, 'Cafétéria Saint-Guillaume venue page', 'https://www.crous-paris.fr/restaurant/cafeteria-saint-guillaume-sciences-po/'],
	[/sciences po|café des sciences/, 'Cafétéria Sciences Po venue page', 'https://www.crous-paris.fr/restaurant/cafeteria-sciences-po-3/'],
	[/ru nation|cafétéria nation/, 'RU Nation venue page', 'https://www.crous-paris.fr/restaurant/ru-nation/'],
	[/nation libre-service/, 'Cafétéria Nation Libre-service venue page', 'https://www.crous-paris.fr/restaurant/cafeteria-nation-libre-service-2/'],
	[/mabillon/, 'RU Mabillon venue page', 'https://www.crous-paris.fr/restaurant/ru-mabillon-3/'],
	[/châtelet|chatelet/, 'RU Châtelet venue page', 'https://www.crous-paris.fr/restaurant/ru-chatelet-3/'],
	[/ru dauphine/, 'RU Dauphine venue page', 'https://www.crous-paris.fr/restaurant/ru-dauphine-3/'],
	[/libre-service dauphine/, 'Libre-service Dauphine venue page', 'https://www.crous-paris.fr/restaurant/libre-service-dauphine/'],
	[/cafétéria dauphine|cafeteria dauphine/, 'Cafétéria Dauphine venue page', 'https://www.crous-paris.fr/restaurant/cafeteria-dauphine-3/'],
	[/clignancourt/, 'RU Clignancourt venue page', 'https://www.crous-paris.fr/restaurant/ru-clignancourt-3/'],
	[/halle aux farines/, 'RU de la Halle aux farines venue page', 'https://www.crous-paris.fr/restaurant/ru-de-la-halle-aux-farines-3/'],
	[/lacretelle|lacrépelle/, 'Cafétéria Lacretelle venue page', 'https://www.crous-paris.fr/restaurant/cafeteria-lacretelle-3/'],
	[/pharmacie/, 'Cafétéria Pharmacie venue page', 'https://www.crous-paris.fr/restaurant/cafeteria-pharmacie-3/'],
	[/cafétéria jourdan|cafeteria jourdan/, 'Cafétéria Jourdan venue page', 'https://www.crous-paris.fr/restaurant/cafeteria-jourdan/'],
	[/portalis/, 'Libre-service Le Portalis venue page', 'https://www.crous-paris.fr/restaurant/libre-service-le-portalis-assas/'],
	[/pierre mendès france|mendes france|pmf/, 'Cafétéria Pierre Mendès France venue page', 'https://www.crous-paris.fr/restaurant/cafeteria-pierre-mendes-france-3/'],
	[/bullier/, 'RU Bullier venue page', 'https://www.crous-paris.fr/restaurant/ru-bullier-3/'],
	[/villemin/, 'Cafétéria Villemin venue page', 'https://www.crous-paris.fr/restaurant/cafeteria-villemin-3/'],
	[/barge/, 'RU de la Barge venue page', 'https://www.crous-paris.fr/restaurant/ru-la-barge-du-crous-de-paris-3/'],
	[/buffon/, 'Restaurant administratif Buffon venue page', 'https://www.crous-paris.fr/restaurant/restaurant-administratif-buffon-3/'],
];

function venuePageFor(p) {
	const text = ((p.name || '') + ' ' + (p.address || '')).toLowerCase();
	for (const [re, label, url] of VENUE_PAGES) if (re.test(text)) return { label, url };
	return null;
}

function parseCroustillantDate(str) {
	if (!str) return new Date();
	const parts = str.split('-');
	if (parts.length === 3) return new Date(parseInt(parts[2]), parseInt(parts[1]) - 1, parseInt(parts[0]));
	return new Date();
}

function formatDateLabel(date) {
	const today = new Date(); today.setHours(0, 0, 0, 0);
	const target = new Date(date); target.setHours(0, 0, 0, 0);
	const diffDays = Math.round((target - today) / (1000 * 60 * 60 * 24));
	if (diffDays === 0) return 'Today';
	if (diffDays === 1) return 'Tomorrow';
	if (diffDays > 1 && diffDays < 7) return date.toLocaleDateString('en-GB', { weekday: 'long' });
	return date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
}

function isPastDate(date) {
	const today = new Date(); today.setHours(0, 0, 0, 0);
	const target = new Date(date); target.setHours(0, 0, 0, 0);
	return target < today;
}

function usableMenus(menus) {
	if (!menus || !Array.isArray(menus)) return [];
	return menus.filter(m => !isPastDate(parseCroustillantDate(m.date)));
}

function campusMapFor(p) {
	const text = ((p.name || '') + ' ' + (p.address || '') + ' ' + ((p.access && p.access.note) || '')).toLowerCase();
	for (const [re, label, url] of CAMPUS_MAPS) if (re.test(text)) return { label, url };
	return null;
}

function resolveMenus(p) {
	if (!p.menu_refs || !Array.isArray(p.menu_refs)) return [];
	return p.menu_refs
		.filter(ref => ref.m != null && GLOBAL_MENUS[ref.m])
		.map(ref => ({ date: ref.date, repas: GLOBAL_MENUS[ref.m], _ref: ref.m }));
}

function renderMenus(menus, p) {
	menus = usableMenus(menus);
	const allSame = menus.length > 1 && menus.every(m => m._ref === menus[0]._ref);
	if (menus.length === 0) return '';

	let html = '<div class="menu-today">';
	if (allSame) {
		const first = formatDateLabel(parseCroustillantDate(menus[0].date));
		const last = formatDateLabel(parseCroustillantDate(menus[menus.length - 1].date));
		html += `<div class="menu-range">Menu ${esc(first)} – ${esc(last)} (unchanged)</div>`;
		menus = [menus[0]];
	} else if (menus.length > 1) {
		html += '<div class="menu-tabs">';
		menus.forEach((m, i) => {
			const label = formatDateLabel(parseCroustillantDate(m.date));
			html += `<button type="button" class="menu-tab ${i === 0 ? 'active' : ''}" data-tab="${i}">${label}</button>`;
		});
		html += '</div>';
	}
	menus.forEach((m, i) => {
		const hidden = (!allSame && i > 0) ? 'display:none;' : '';
		html += `<div class="menu-content" data-tab="${i}" style="${hidden}">`;
		for (const repas of m.repas) {
			const mealType = repas.type === 'soir' ? 'Dinner' : (repas.type === 'midi' ? 'Lunch' : repas.type);
			html += `<div class="meal"><i>${esc(mealType)}</i>`;
			for (const cat of repas.categories) {
				const items = cat.plats.map(p => esc(p)).join(', ');
				html += `<div class="cat"><b>${esc(cat.libelle)}:</b> ${items}</div>`;
			}
			html += `</div>`;
		}
		html += '</div>';
	});
	let creditUrl = 'https://croustillant.menu';
	if (p && p.croustillant_code && p.croustillant_slug) {
		creditUrl = `https://croustillant.menu/fr/restaurants/${p.croustillant_slug}-r${p.croustillant_code}`;
	}
	html += `<div class="menu-credit">Data from <a href="${creditUrl}" target="_blank" rel="noopener">CROUStillant</a></div>`;
	html += '</div>';
	return html;
}

document.addEventListener('click', (e) => {
	if (e.target.classList.contains('menu-tab')) {
		const popup = e.target.closest('.leaflet-popup-content-wrapper');
		if (!popup) return;
		const tabs = popup.querySelectorAll('.menu-tab');
		const contents = popup.querySelectorAll('.menu-content');
		const idx = e.target.dataset.tab;
		tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === idx));
		contents.forEach(c => c.style.display = c.dataset.tab === idx ? 'block' : 'none');
	}
});

function canEnter(p, prof) {
	if (!prof.uni) return true; // no filter
	const uni = UNIS.find(u => u[0] === prof.uni);
	if (!uni) return true;
	const text = (((p.access && p.access.note) || '') + ' ' + (p.name || '')).toLowerCase();
	const mine = uni[2].test(text);
	const lvl = (p.access && p.access.level) || 'unknown';
	if (prof.staff) {
		if (lvl === 'staff') return mine || GENERIC_STAFF_RE.test(text);
		if (lvl === 'restricted') return /personnel/.test(text) && mine;
		return true;
	}
	if (lvl === 'staff') return false; // staff-only venue, student profile
	if (lvl === 'restricted') return mine;
	return true; // open to all students / unknown
}

function hexToRgba(hex, a) {
	const n = parseInt(hex.slice(1), 16);
	return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

const map = L.map('map', {
	preferCanvas: true,
	center: CONFIG.center, zoom: CONFIG.zoom, minZoom: 10, maxZoom: 17,
	dragging: true, scrollWheelZoom: true, doubleClickZoom: true,
	touchZoom: true, keyboard: true, boxZoom: true,
});

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
	maxZoom: 19,
	attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors | data: MESR, OSM (ODbL), Bien\'ici, SeLoger',
}).addTo(map);

const fmtMin = m => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
const fmtDur = m => m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')}` : `${m} min`;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
	({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
const trunc = (s, n) => (s && s.length > n) ? s.slice(0, n - 1) + '...' : s;
const fmtPrice = p => p != null ? p.toLocaleString('fr-FR') + ' €' : 'n/a';

/* current Paris time, incl. full date for holiday handling */
function parisNow() {
	const parts = new Intl.DateTimeFormat('en-GB', {
		timeZone: 'Europe/Paris', weekday: 'short', hour: '2-digit', minute: '2-digit',
		year: 'numeric', month: '2-digit', day: '2-digit', hour12: false,
	}).formatToParts(new Date());
	const g = t => parts.find(p => p.type === t).value;
	let h = parseInt(g('hour'), 10); if (h === 24) h = 0;
	return { day: WD_SHORT[g('weekday')], minute: h * 60 + parseInt(g('minute'), 10),
					 year: +g('year'), month: +g('month'), dom: +g('day') };
}

/* French public holidays: 8 fixed + Easter Monday, Ascension, Whit Monday (11 total) */
function easterSunday(y) {
	const a = y % 19, b = Math.floor(y / 100), c = y % 100;
	const d = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25);
	const g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30;
	const i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7;
	const m = Math.floor((a + 11 * h + 22 * l) / 451);
	return [Math.floor((h + l - 7 * m + 114) / 31), ((h + l - 7 * m + 114) % 31) + 1];
}

function publicHoliday(y, m, d) {
	const FIXED = { 101:"new year's day", 501:'labour day', 508:'VE day', 714:'bastille day',
									815:'assumption', 1101:'all saints', 1111:'armistice', 1225:'christmas' };
	const key = m * 100 + d;
	if (FIXED[key]) return FIXED[key];
	const [em, ed] = easterSunday(y);
	const shift = n => { const t = new Date(y, em - 1, ed + n); return [t.getMonth() + 1, t.getDate()]; };
	if ([1, 39, 50].some(n => { const t = shift(n); return t[0] === m && t[1] === d; })) {
		const n = [1, 39, 50].find(n => { const t = shift(n); return t[0] === m && t[1] === d; });
		return n === 1 ? 'easter monday' : n === 39 ? 'ascension' : 'whit monday';
	}
	return null;
}

/* rough usual closure windows - term-time data cannot do better than a warning */
function seasonNote(m, d) {
	if (m === 8)
		return 'August closure - nearly all CROUS venues are closed for the entire month';
	if ((m === 7 && d >= 15) || (m === 9 && d <= 5))
		return 'Summer period - reduced service, some venues may be closed';
	if ((m === 12 && d >= 23) || (m === 1 && d <= 2))
		return 'Year-end break - CROUS venues typically closed until early January';
	if ((m === 4 && d >= 20) || (m === 5 && d <= 5))
		return 'Spring break - hours depend on the specific university calendar';
	return null;
}

function statusOf(p, now) {
	if (p.closure_status === 'confirmed')
		return { state: 'confirmed', label: 'Long-term closure (works/renovation) - see notice' };
	const sched = p.schedule || {};
	for (const [o, c] of (sched[String(now.day)] || [])) {
		if (now.minute >= o && now.minute < c) {
			const left = c - now.minute;
			return { state: 'open', left, label: `Open now - closes at ${fmtMin(c)} (in ${fmtDur(left)})` };
		}
	}
	for (let d = 0; d < 7; d++) {
		const day = (now.day + d) % 7;
		for (const [o] of (sched[String(day)] || []).slice().sort((a, b) => a[0] - b[0])) {
			if (d === 0 && o <= now.minute) continue;
			const delta = d * 1440 + o - now.minute;
			const when = d === 0 ? 'today' : d === 1 ? 'tomorrow' : WD[day];
			if (delta <= CONFIG.opensSoonMin)
				return { state: 'opens_soon', label: `Closed - opens ${when} at ${fmtMin(o)} (in ${fmtDur(delta)})` };
			return { state: 'closed', label: `Closed - opens ${when} at ${fmtMin(o)}` };
		}
	}
	return { state: 'unknown', label: 'Opening hours unknown - see details' };
}

function colorFor(s) {
	if (s.state === 'open') {
		if (s.left >= CONFIG.darkGreenMin) return COLORS.dark_green;
		if (s.left >= CONFIG.greenMin) return COLORS.green;
		return COLORS.yellow;
	}
	if (s.state === 'opens_soon') return COLORS.blue;
	if (s.state === 'closed') return COLORS.red;
	if (s.state === 'confirmed') return COLORS.confirmed;
	return COLORS.unknown;
}

function groupStatus(statuses) {
	let best = statuses[0];
	for (const s of statuses) if (RANK[s.state] > RANK[best.state]) best = s;
	if (best.state === 'open')
		for (const s of statuses) if (s.state === 'open' && s.left > best.left) best = s;
	return best;
}

function accessBadge(a) {
	if (!a) return '';
	if (a.level === 'all') return `<span class="badge ok">open to ALL students</span>`;
	if (a.level === 'staff') return `<span class="badge staff">staff only${a.note ? ': ' + esc(trunc(a.note, 70)) : ''}</span>`;
	if (a.level === 'restricted') return `<span class="badge warn">restricted${a.note ? ': ' + esc(trunc(a.note, 70)) : ''}</span>`;
	const fallback = profile.staff ? 'no access info - verify on site' : 'no access info (CROUS default: all students)';
	return `<span class="badge muted">${a.note ? esc(trunc(a.note, 70)) : fallback}</span>`;
}

function venueHtml(p, s, ok) {
	let notices = '';
	if (p.closure_status === 'confirmed')
		notices += `<div class="warn">[!] ${esc(p.description || p.closure_notice || 'Closed for renovation - verify locally')}</div>`;
	else if (p.closure_status === 'notice_only' && p.closure_notice)
		notices += `<div class="notice">[i] ${esc(p.closure_notice)}</div>`;
	else if (p.description)
		notices += `<div class="desc">${esc(p.description)}</div>`;
	if ((p.conditional_days || []).length)
		notices += `<div class="notice">[i] ${p.conditional_days.map(d => WD[d]).join(', ')} opening depends on the university calendar</div>`;
	const menuHtml = renderMenus(resolveMenus(p), p);
	const dimBadge = ok ? '' : `<span class="badge dim">not accessible with your profile</span>`;
	const cm = campusMapFor(p);
	const venuePage = venuePageFor(p);
	let croustillantLink = '';
	if (p.croustillant_code && p.croustillant_slug) {
		croustillantLink = ` | <a href="https://croustillant.menu/fr/restaurants/${p.croustillant_slug}-r${p.croustillant_code}" target="_blank" rel="noopener">CROUStillant page</a>`;
	}
	const gmaps = `https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lon}`;
	return `<h3>${esc(p.name)}</h3>
		<div class="badges"><span class="badge type">${esc(p.type || '?')}</span>${accessBadge(p.access)}${dimBadge}</div>
		<div class="status" style="color:${colorFor(s)}">* ${esc(s.label)}</div>
		${notices}
		${menuHtml}
		<div class="addr">${esc(p.address || '')}${p.zone ? ' - ' + esc(p.zone) : ''}</div>
		<div class="hours"><b>Hours (as published):</b> ${esc(p.hours_raw || 'n/a')}
				${p.schedule_confidence === 'unparsed' ? '<i> (could not parse - check raw text)</i>' : ''}</div>
		<div class="src">
				<a href="https://www.crous-paris.fr/se-restaurer/carte/" target="_blank" rel="noopener">CROUS Paris map</a>
				${venuePage ? ` | <a href="${venuePage.url}" target="_blank" rel="noopener">${esc(venuePage.label)}</a>` : ''}
				${croustillantLink}
				${cm ? ` | <a href="${cm.url}" target="_blank" rel="noopener">${esc(cm.label)}</a>` : ''}
				| <a href="${gmaps}" target="_blank" rel="noopener">directions</a>
		</div>`;
}

function popupHtml(places, statuses, oks) {
	const items = places.map((p, i) => ({ p, s: statuses[i], ok: oks[i] }));
	items.sort((a, b) => {
		if (a.ok !== b.ok) return a.ok ? -1 : 1; // accessible first
		const ra = RANK[a.s.state] || 0, rb = RANK[b.s.state] || 0;
		if (ra !== rb) return rb - ra; // open > opens_soon > closed > ...
		if (a.s.state === 'open' && b.s.state === 'open') return b.s.left - a.s.left;
		return a.p.name.localeCompare(b.p.name);
	});
	let html = '<div class="pop">';
	items.forEach((it, i) => {
		if (i > 0) html += '<hr class="sep">';
		html += venueHtml(it.p, it.s, it.ok);
	});
	html += '</div>';
	return html;
}

// APARTMENT LAYER

let allApartments = [];

function apartmentPassesFilter(l) {
	const price = l.price || 0;
	const surface = l.surface_m2 || 0;
	const rooms = l.rooms || 0;

	if (price < aptFilter.priceMin || price > aptFilter.priceMax) return false;
	if (surface < aptFilter.surfaceMin) return false;
	if (rooms < aptFilter.roomsMin) return false;
	if (aptFilter.energyClass && (l.energy_class || '').toUpperCase() !== aptFilter.energyClass) return false;
	if (aptFilter.onlyMultiSource && !l.sources) return false;
	return true;
}

function applyApartmentFilters() {
	layers.apartments.markers.forEach(m => map.removeLayer(m));
	layers.apartments.markers = [];

	if (layers.apartments.blurDisk) {
		map.removeLayer(layers.apartments.blurDisk);
		layers.apartments.blurDisk = null;
	}

	// Hide apartments entirely if zoomed out too far
	if (!layers.apartments.visible || map.getZoom() < 13) {
		updateFilterCounts();
		return; 
	}

	const filtered = allApartments.filter(apartmentPassesFilter);
	layers.apartments.filtered = filtered.length;

	const bounds = map.getBounds().pad(0.2);
	for (const l of filtered) {
		if (!bounds.contains([l.lat, l.lon])) continue;
		const priceLabel = l.price >= 1000
		? Math.floor(l.price / 100) / 10 + 'k'
		: String(l.price);
		const isMulti = !!l.sources;
		const bgColor = isMulti ? '#c62828' : '#1565c0';
		const icon = L.divIcon({
			className: 'apt-marker-wrapper',
			html: `<div class="apt-marker ${isMulti ? 'multi-source' : ''}"
									style="background:${bgColor}">${priceLabel}</div>`,
			iconSize: [34, 22], iconAnchor: [17, 11],
		});
		const marker = L.marker([l.lat, l.lon], { icon })
			.bindPopup(() => apartmentPopup(l), { className: 'mobile-popup apt-popup', maxWidth: 340 })
			.addTo(map);

		// Show blur disk on popup open, hide on close
		marker.on('popupopen', () => {
			if (layers.apartments.blurDisk) map.removeLayer(layers.apartments.blurDisk);
			const radius = l.blur_radius || 250;
			layers.apartments.blurDisk = L.circle([l.lat, l.lon], {
				radius: radius,
				color: '#1565c0',
				weight: 1.5,
				fillColor: '#1565c0',
				fillOpacity: 0.12,
				dashArray: '6 4',
			}).addTo(map);
		});
		marker.on('popupclose', () => {
			if (layers.apartments.blurDisk) {
				map.removeLayer(layers.apartments.blurDisk);
				layers.apartments.blurDisk = null;
			}
		});
		layers.apartments.markers.push(marker);
	}
	updateFilterCounts();
}

function stripHtml(str) {
	if (!str) return '';
	return str
		.replace(/<br\s*\/?>/gi, ' ')
		.replace(/<[^>]*>/g, '')
		.replace(/&nbsp;/g, ' ')
		.replace(/&amp;/g, '&')
		.replace(/&lt;/g, '<')
		.replace(/&gt;/g, '>')
		.replace(/&#39;/g, "'")
		.replace(/\s+/g, ' ')
		.trim();
}

function apartmentPopup(l) {
	const dpeColor = DPE_COLORS[(l.energy_class || '').toUpperCase()] || '#999';
	const blurNote = `<div class="fine" style="margin-top:4px;color:#888;"> Position approximate - source blurs exact location</div>`;
	const dpeBadge = l.energy_class
		? `<span class="apt-energy" style="background:${dpeColor}">${esc(l.energy_class.toUpperCase())}</span>` : '';

	let sourcesHtml = '';
	if (l.sources) {
		sourcesHtml = `<div class="apt-sources"><b>Found on ${l.sources.length} sites:</b><br>` +
			l.sources.map(s => `<a href="${esc(s.url)}" target="_blank" rel="noopener">
				<span class="badge source">${esc(s.source)}</span></a>`).join('') + '</div>';
	} else {
		sourcesHtml = `<div class="apt-sources">
			<a href="${esc(l.url)}" target="_blank" rel="noopener">
				<span class="badge source">${esc(l.source)}</span> View listing →</a></div>`;
	}

	const photoHtml = (l.photos && l.photos[0])
		? `<img class="apt-photo" src="${esc(l.photos[0])}" alt="" loading="lazy"
						onerror="this.style.display='none'">` : '';

	return `<div class="pop">
		<h3>${esc(l.title || 'Apartment')}</h3>
		${l.sources ? '<span class="badge multi">multi-source listing</span>' : ''}
		<div class="apt-price">${fmtPrice(l.price)} <small>/month</small></div>
		${photoHtml}
		<dl class="apt-details">
			<dt>Surface</dt><dd>${l.surface_m2 ? l.surface_m2 + ' m²' : 'n/a'}</dd>
			<dt>Rooms</dt><dd>${l.rooms || 'n/a'}</dd>
			<dt>Bedrooms</dt><dd>${l.bedrooms || 'n/a'}</dd>
			<dt>DPE</dt><dd>${dpeBadge || 'n/a'}</dd>
			<dt>Furnished</dt><dd>${l.furnished == null ? 'n/a' : l.furnished ? 'Yes' : 'No'}</dd>
			<dt>Area</dt><dd>${esc(l.district || l.postal_code || 'Paris')}</dd>
		</dl>
		${l.description ? `<div class="desc">${esc(trunc(stripHtml(l.description), 250))}</div>` : ''}
		${sourcesHtml}
		${l.agency ? `<div class="fine">Agency: ${esc(l.agency)}</div>` : ''}
		${blurNote}
	</div>`;
}

function initApartmentLayer(data) {
	allApartments = (data.listings || []).filter(l => l.lat && l.lon);
	layers.apartments.count = allApartments.length;
	applyApartmentFilters();
}

// AMENITY LAYER

let allAmenities = [];

function initAmenityLayer(data) {
	allAmenities = data.amenities || [];
	layers.amenities.count = allAmenities.length;

	// Initialise sub-category visibility (all on by default)
	for (const a of allAmenities) {
		if (!(a.category in amenityVisible)) amenityVisible[a.category] = true;
	}

	renderAmenityMarkers();
}

function renderAmenityMarkers() {
	layers.amenities.markers.forEach(m => map.removeLayer(m));
	layers.amenities.markers = [];

	if (!layers.amenities.visible) return;

	const bounds = map.getBounds().pad(0.15);
	const zoom = map.getZoom();

	// Hide minor categories when zoomed out
	const skipAtLowZoom = zoom < 14 
		? new Set(['cheese', 'seafood', 'butcher', 'greengrocer', 'laundry', 'zero_waste', 'health_food'])
		: new Set();

	// Adjust marker size based on zoom level
	const radius = zoom >= 15 ? 6 : (zoom >= 14 ? 5 : 4);

	for (const a of allAmenities) {
		if (!amenityVisible[a.category]) continue;
		if (skipAtLowZoom.has(a.category)) continue;
		if (!bounds.contains([a.lat, a.lon])) continue;

		const color = AMENITY_COLORS[a.category] || '#757575';
		
		const marker = L.circleMarker([a.lat, a.lon], {
			radius: radius,
			fillColor: color,
			color: '#ffffff',
			weight: 1.5,
			opacity: 1,
			fillOpacity: 0.85
		});

		marker.bindPopup(() => amenityPopup(a), { className: 'mobile-popup amenity-popup', maxWidth: 300 });
		marker.addTo(map);
		layers.amenities.markers.push(marker);
	}
}

// Re-render amenities on map move/zoom (debounced)
let amenityRenderTimer = null;
let renderTimer = null;
map.on('moveend zoomend', () => {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(() => {
    if (layers.amenities.visible) renderAmenityMarkers();
    if (layers.apartments.visible) applyApartmentFilters();
  }, 150); // 150ms debounce
});

function amenityPopup(a) {
	const color = AMENITY_COLORS[a.category] || '#757575';
	let tags = '';
	if (a.vegan_friendly) tags += '<span class="amenity-tag vegan">vegan</span>';
	if (a.vegetarian_friendly) tags += '<span class="amenity-tag vegan">vegetarian</span>';
	if (a.organic) tags += '<span class="amenity-tag organic">organic</span>';
	if (a.wheelchair === 'yes') tags += '<span class="amenity-tag wheelchair">wheelchair accessible</span>';

	const gmaps = `https://www.google.com/maps/search/?api=1&query=${a.lat},${a.lon}`;

	return `<div class="pop">
		<span class="amenity-cat" style="background:${color}">${esc(a.category_label)}</span>
		<h3>${esc(a.name)}</h3>
		${tags ? `<div class="amenity-tags">${tags}</div>` : ''}
		${a.brand ? `<div class="addr">Brand: ${esc(a.brand)}</div>` : ''}
		${a.address ? `<div class="addr">${esc(a.address)}</div>` : ''}
		${a.opening_hours ? `<div class="amenity-hours">${esc(a.opening_hours)}</div>` : ''}
		${a.phone ? `<div class="addr">${esc(a.phone)}</div>` : ''}
		<div class="src">
			${a.website ? `<a href="${esc(a.website)}" target="_blank" rel="noopener">website</a> | ` : ''}
			<a href="${gmaps}" target="_blank" rel="noopener">directions</a> |
			<a href="https://www.openstreetmap.org/${a.id.replace('osm-','')}" target="_blank" rel="noopener">OSM</a>
		</div>
	</div>`;
}

// LAYER VISIBILITY

function setLayerVisible(name, visible) {
	layers[name].visible = visible;

	if (name === 'cafeterias') {
		for (const it of layers.cafeterias.items) {
			if (visible) it.marker.addTo(map);
			else map.removeLayer(it.marker);
		}
	} else if (name === 'apartments') {
		if (visible) applyApartmentFilters();
		else layers.apartments.markers.forEach(m => map.removeLayer(m));
	} else if (name === 'amenities') {
		renderAmenityMarkers();
	}
}

// CAFETERIA LAYER

let GLOBAL_MENUS = [];
let totalVenues = 0;
let generatedAt = null;

function initCafeteriaLayer(data) {
	generatedAt = data.generated_at ? Date.parse(data.generated_at) : null;
	GLOBAL_MENUS = data.menus || [];

	const dl = document.getElementById('data-line');
	if (dl && data.generated_at) dl.textContent = `CROUS data: ${data.generated_at.slice(0, 10)}`;

	/* group venues that sit on the same spot (rounded to ~1 m) into ONE marker */
	const groups = new Map();
	for (const p of data.places) {
		const k = p.lat.toFixed(CONFIG.groupDecimals) + ',' + p.lon.toFixed(CONFIG.groupDecimals);
		if (!groups.has(k)) groups.set(k, { lat: 0, lon: 0, places: [] });
		const g = groups.get(k);
		g.places.push(p);
		g.lat += p.lat; g.lon += p.lon;
	}
	for (const g of groups.values()) { g.lat /= g.places.length; g.lon /= g.places.length; }

	for (const g of groups.values()) {
		const size = g.places.length > 1 ? 26 : 22; // slightly larger for multi-venue
		const icon = L.divIcon({
			className: 'pie-marker-wrapper',
			html: '<div class="pie-marker"></div>',
			iconSize: [size, size],
			iconAnchor: [size / 2, size / 2],
		});
		const marker = L.marker([g.lat, g.lon], { icon });
		const item = { places: g.places, marker, size,
									 names: g.places.map(p => p.name).join(' / '), lastHtml: '' };
		/* content is (re)computed lazily at open time */
		marker.bindPopup(() => popupHtml(item.places,
			item.places.map(p => statusOf(p, parisNow())),
			item.places.map(p => canEnter(p, profile))),
			{ autoPan: true, className: 'mobile-popup', maxWidth: 360 });
		layers.cafeterias.items.push(item);
	}
	totalVenues = data.places.length;
	layers.cafeterias.count = totalVenues;
	setLayerVisible('cafeterias', layers.cafeterias.visible);
}

// TITLE CONTROL

const title = L.control({ position: 'topright' });
title.onAdd = () => {
	const d = L.DomUtil.create('div', 'leaflet-control box title');
	d.innerHTML = `<b>Student Paris</b>
		<span id="clock"></span>
		<span id="total" class="fine"></span>
		<span id="season" class="fine"></span>
		<span id="headline" class="fine"></span>`;
	return d;
};
title.addTo(map);

const LEGEND = [
	['dark_green', 'Open - closes in 2 h+'],
	['green', 'Open - closes in 1-2 h'],
	['yellow', 'Open - closes in < 1 h'],
	['blue', 'Closed - opens within 1 h'],
	['red', 'Closed'],
	['confirmed', 'Long-term closure'],
	['unknown', 'Hours unknown'],
];

/* collapsible menu: layer toggles + filters + profile + legend */
const panel = L.control({ position: 'bottomright' });
panel.onAdd = () => {
	const d = L.DomUtil.create('div', 'leaflet-control box panel');
	d.innerHTML =
		`<button id="panel-toggle" class="panel-btn" type="button">[ menu ]</button>
		<div id="panel-body" class="panel-body hidden">
			<div class="fine" id="data-line"></div>
			<div class="fine warn-line" id="stale-line" style="display:none">data seems stale - the refresh workflow may have failed</div>

			<!-- LAYER TOGGLES -->
			<div class="panel-sec layer-toggles"><b>map layers</b>
				<label class="layer-toggle">
					<input type="checkbox" id="lyr-cafeterias" checked>
					<span class="layer-icon" style="background:#00a650">C</span>
					Cafeterias <span class="layer-count" id="cnt-cafeterias"></span>
				</label>
				<label class="layer-toggle">
					<input type="checkbox" id="lyr-apartments" checked>
					<span class="layer-icon" style="background:#1565c0">A</span>
					Apartments <span class="layer-count" id="cnt-apartments"></span>
				</label>
				<label class="layer-toggle">
					<input type="checkbox" id="lyr-amenities" checked>
					<span class="layer-icon" style="background:#8e24aa">S</span>
					Daily amenities <span class="layer-count" id="cnt-amenities"></span>
				</label>
				<div class="amenity-sub" id="amenity-sub"></div>
			</div>

			<!-- APARTMENT FILTERS -->
			<div class="panel-sec apt-filters" id="apt-filters"><b>apartment search</b>
				<div class="apt-filter-row">
					<label>Min price</label>
					<input type="range" id="apt-price-min" min="0" max="2000" step="50" value="0">
					<span class="val" id="apt-price-min-val">0 €</span>
				</div>
				<div class="apt-filter-row">
					<label>Max price</label>
					<input type="range" id="apt-price-max" min="200" max="5000" step="50" value="5000">
					<span class="val" id="apt-price-max-val">5000 €</span>
				</div>
				<div class="apt-filter-row">
					<label>Min surface</label>
					<input type="range" id="apt-surface" min="0" max="80" step="5" value="0">
					<span class="val" id="apt-surface-val">0 m²</span>
				</div>
				<div class="apt-filter-row">
					<label>Min rooms</label>
					<select id="apt-rooms">
						<option value="0">Any</option>
						<option value="1">1+</option>
						<option value="2">2+</option>
						<option value="3">3+</option>
						<option value="4">4+</option>
					</select>
				</div>
				<div class="apt-filter-row">
					<label>DPE class</label>
					<select id="apt-dpe">
						<option value="">Any</option>
						<option value="A">A (best)</option>
						<option value="B">B</option>
						<option value="C">C</option>
						<option value="D">D</option>
						<option value="E">E</option>
						<option value="F">F</option>
						<option value="G">G (worst)</option>
					</select>
				</div>
				<label class="chk">
					<input type="checkbox" id="apt-multi"> Only multi-source listings
				</label>
				<div class="fine" id="apt-result-line"></div>
			</div>

			<!-- PROFILE (cafeteria filter) -->
			<div class="panel-sec"><b>cafeteria profile</b>
				<select id="uni-select" aria-label="university">
					<option value="">no filter - show all venues</option>
					${UNIS.map(u => `<option value="${u[0]}">${esc(u[1])}</option>`).join('')}
				</select>
				<label class="chk"><input type="checkbox" id="staff-chk"> I am staff (not student)</label>
				<div class="fine" id="filtered-line"></div>
			</div>

			<!-- LEGEND -->
			<div class="panel-sec"><b>cafeteria legend</b>
				${LEGEND.map(([k, l]) =>
					`<div class="legend-row" id="row-${k}"><span class="dot" style="background:${COLORS[k]}"></span>${l} <span class="cnt" id="cnt-${k}"></span></div>`).join('')}
			</div>
			<div class="fine">auto-refresh ${CONFIG.refreshSec}s - Europe/Paris time</div>
		</div>`;
	L.DomEvent.disableClickPropagation(d);
	L.DomEvent.disableScrollPropagation(d);
	return d;
};
panel.addTo(map);

/* Panel event wiring */

document.getElementById('panel-toggle').addEventListener('click', () => {
	const body = document.getElementById('panel-body');
	const hidden = body.classList.toggle('hidden');
	document.getElementById('panel-toggle').textContent = hidden ? '[ menu ]' : '[ close ]';
});

// Layer toggles
for (const name of ['cafeterias', 'apartments', 'amenities']) {
	document.getElementById('lyr-' + name).addEventListener('change', e => {
		setLayerVisible(name, e.target.checked);
		// Show/hide apartment filters
		if (name === 'apartments') {
			document.getElementById('apt-filters').classList.toggle('hidden', !e.target.checked);
		}
		tick();
	});
}

// Apartment filters
// Apartment filters
document.getElementById('apt-price-min').addEventListener('input', e => {
	aptFilter.priceMin = +e.target.value;
	document.getElementById('apt-price-min-val').textContent = e.target.value + ' €';
	applyApartmentFilters();
});
document.getElementById('apt-price-max').addEventListener('input', e => {
	aptFilter.priceMax = +e.target.value;
	document.getElementById('apt-price-max-val').textContent = e.target.value + ' €';
	applyApartmentFilters();
});
document.getElementById('apt-surface').addEventListener('input', e => {
	aptFilter.surfaceMin = +e.target.value;
	document.getElementById('apt-surface-val').textContent = e.target.value + ' m²';
	applyApartmentFilters();
});
document.getElementById('apt-rooms').addEventListener('change', e => {
	aptFilter.roomsMin = +e.target.value;
	applyApartmentFilters();
});
document.getElementById('apt-dpe').addEventListener('change', e => {
	aptFilter.energyClass = e.target.value;
	applyApartmentFilters();
});
document.getElementById('apt-multi').addEventListener('change', e => {
	aptFilter.onlyMultiSource = e.target.checked;
	applyApartmentFilters();
});

// Profile (cafeteria filter)
document.getElementById('uni-select').addEventListener('change', e => {
	profile.uni = e.target.value || null;
	tick();
});
document.getElementById('staff-chk').addEventListener('change', e => {
	profile.staff = e.target.checked;
	tick();
});

/* Dynamic amenity sub-toggles */
function buildAmenitySubToggles() {
	const container = document.getElementById('amenity-sub');
	const cats = {};
	for (const a of allAmenities) {
		if (!cats[a.category]) cats[a.category] = { label: a.category_label, count: 0 };
		cats[a.category].count++;
	}
	let html = '';
	for (const [cat, info] of Object.entries(cats).sort((a, b) => b[1].count - a[1].count)) {
		const color = AMENITY_COLORS[cat] || '#757575';
		html += `<label class="layer-toggle">
			<input type="checkbox" data-amcat="${cat}" checked>
			<span class="dot" style="background:${color};width:10px;height:10px"></span>
			${esc(info.label)} <span class="layer-count">(${info.count})</span>
		</label>`;
	}
	container.innerHTML = html;
	container.querySelectorAll('input[data-amcat]').forEach(cb => {
		cb.addEventListener('change', e => {
			amenityVisible[e.target.dataset.amcat] = e.target.checked;
			renderAmenityMarkers();
		});
	});
}

function updateFilterCounts() {
	const el = document.getElementById('apt-result-line');
	if (el) el.textContent = `showing ${layers.apartments.filtered} of ${layers.apartments.count} listings`;
	const cnt = document.getElementById('cnt-apartments');
	if (cnt) cnt.textContent = `(${layers.apartments.filtered})`;
}

// DATA LOADING (Promise.allSettled for independent layers)

Promise.allSettled([
	fetch('data/paris.json').then(r => r.ok ? r.json() : Promise.reject(r.status)),
	fetch('data/apartments.json').then(r => r.ok ? r.json() : Promise.reject(r.status)),
	fetch('data/amenities.json').then(r => r.ok ? r.json() : Promise.reject(r.status)),
]).then(([crousRes, aptRes, amenRes]) => {
	if (crousRes.status === 'fulfilled') {
		initCafeteriaLayer(crousRes.value);
	} else {
		console.warn('Could not load CROUS data:', crousRes.reason);
	}

	if (aptRes.status === 'fulfilled') {
		initApartmentLayer(aptRes.value);
	} else {
		console.warn('Could not load apartment data:', aptRes.reason);
	}

	if (amenRes.status === 'fulfilled') {
		initAmenityLayer(amenRes.value);
		buildAmenitySubToggles();
	} else {
		console.warn('Could not load amenity data:', amenRes.reason);
	}

	// Update header counts
	const el = document.getElementById('total');
	if (el) {
		const parts = [];
		if (layers.cafeterias.count) parts.push(`${layers.cafeterias.count} cafeterias`);
		if (layers.apartments.count) parts.push(`${layers.apartments.count} flats`);
		if (layers.amenities.count) parts.push(`${layers.amenities.count} shops`);
		el.textContent = parts.join(' · ');
	}

	document.getElementById('cnt-cafeterias').textContent = `(${layers.cafeterias.count})`;
	document.getElementById('cnt-amenities').textContent = `(${layers.amenities.count})`;
	updateFilterCounts();

	tick();
	setInterval(tick, CONFIG.refreshSec * 1000);
});

// TICK

function tick() {
	const now = parisNow();
	const counts = Object.fromEntries(Object.keys(COLORS).map(k => [k, 0]));
	let filtered = 0, openCount = 0, accessibleCount = 0;

	if (layers.cafeterias.visible) {
		for (const it of layers.cafeterias.items) {
			const statuses = it.places.map(p => statusOf(p, now));
			const oks = it.places.map(p => canEnter(p, profile));
			filtered += oks.filter(o => !o).length;
			openCount += statuses.filter(s => s.state === 'open').length;
			accessibleCount += oks.filter(Boolean).length;

			const pool = statuses.filter((_, i) => oks[i]); // accessible venues only
			const dim = pool.length === 0; // nothing accessible at this spot
			const best = groupStatus(pool.length ? pool : statuses);

			/* one pie slice per venue; ghost slice (15% opacity) when not accessible */
			const step = 100 / statuses.length;
			const stops = statuses.map((s, i) => {
				const col = colorFor(s);
				return `${oks[i] ? col : hexToRgba(col, 0.15)} ${(i * step).toFixed(2)}% ${((i + 1) * step).toFixed(2)}%`;
			});
			const el = it.marker.getElement();
			if (el) {
				const pie = el.querySelector('.pie-marker');
				if (pie) {
					pie.style.background = `conic-gradient(${stops.join(', ')})`;
					pie.classList.toggle('dim', dim);
				}
			}

			const tooltipText = `${it.names} - ${best.label}${dim ? ' [filtered out]' : ''}`;
			if (!it.tooltipBound) {
				it.marker.bindTooltip(tooltipText, { direction: 'top', offset: [0, -it.size / 2] });
				it.tooltipBound = true;
			} else {
				it.marker.setTooltipContent(tooltipText);
			}

			/* refresh an OPEN popup only when its content actually changed */
			if (it.marker.isPopupOpen()) {
				const html = popupHtml(it.places, statuses, oks);
				if (html !== it.lastHtml) {
					it.marker.getPopup().setContent(html);
					it.lastHtml = html;
				}
			}

			/* legend: count accessible venues individually */
			if (!dim) for (const s of pool) counts[COLOR_KEY[colorFor(s)]]++;
		}
	}

	for (const [k] of LEGEND) {
		const el = document.getElementById('cnt-' + k);
		if (el) el.textContent = counts[k] ? `(${counts[k]})` : '';
		const row = document.getElementById('row-' + k);
		if (row) row.classList.toggle('empty', counts[k] === 0); // grey out zero rows
	}

	const fl = document.getElementById('filtered-line');
	if (fl) fl.textContent = profile.uni ? `filtered out: ${filtered} of ${totalVenues} venues` : '';

	const hl = document.getElementById('headline');
	if (hl) {
		const parts = [];
		if (layers.cafeterias.visible && openCount) parts.push(`${openCount} cafeterias open`);
		if (layers.apartments.visible) parts.push(`${layers.apartments.filtered} flats shown`);
		if (layers.amenities.visible) parts.push(`${layers.amenities.markers.length} amenities`);
		hl.textContent = parts.join(' · ') || '';
	}

	const seasonEl = document.getElementById('season');
	if (seasonEl) {
		const holiday = publicHoliday(now.year, now.month, now.dom);
		seasonEl.textContent = holiday ? `public holiday (${holiday}) - hours may differ`
			: (seasonNote(now.month, now.dom) || '');
	}

	const sl = document.getElementById('stale-line');
	if (sl) sl.style.display =
		(generatedAt && Date.now() - generatedAt > CONFIG.staleHours * 3600 * 1000) ? '' : 'none';

	const el = document.getElementById('clock');
	if (el) el.textContent = `Paris time: ${fmtMin(now.minute)} - ${WD[now.day]}`;
}