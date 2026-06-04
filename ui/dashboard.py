"""
dashboard.py — SGS v4
Financial Dashboard with month filter.

Month filter (top toolbar) lets the user select any school month or "Mois en cours".
All KPI sections (Students, Revenue, Expenses, Salaries, Profit) react to the selection.
Charts always display the full year for context; the selected month is highlighted.

KPI Sections:
  1. Students      : Total / Paid (selected month) / Unpaid / Outstanding debt
  2. Revenue       : Expected / Collected / Gap  — for the selected month
  3. Insurance     : Collected (school year) / Students without insurance
  4. Expenses      : Expected / Paid / Remaining  — for the selected month
  5. Salaries      : Total employees / Paid / Pending / Amount paid
  6. Monthly Profit: Revenue + Transport − Expenses − Salaries  (insurance excluded)

Charts (full-year):
  A. Monthly Profit Evolution  — selected month highlighted
  B. Revenue vs Expenses       — selected month highlighted
  C. Student Payment Rate      — NAN excluded
  D. Class Breakdown           — pie
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGridLayout, QScrollArea, QSizePolicy, QPushButton, QComboBox
)
from PySide6.QtCore import Qt
from datetime import datetime

try:
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    HAS_MPL = True
except Exception:
    HAS_MPL = False

from models.database import (
    Student, Payment, MonthRecord, Employee, Salary,
    Setting, ExpenseCategory, ExpensePayment, SCHOOL_MONTHS
)
from themes.style import (
    PRIMARY, PRIMARY_LIGHT, SUCCESS, SUCCESS_LIGHT, DANGER, DANGER_LIGHT,
    WARNING, WARNING_LIGHT, INFO, INFO_LIGHT, PURPLE, PURPLE_LIGHT,
    PINK, PINK_LIGHT, TEAL, TEAL_LIGHT,
    BG_CARD, BORDER, TEXT_MAIN, TEXT_SUB,
    REINSCRIPTION_LABELS, REINSCRIPTION_COLORS,
    SCHOOL_MONTHS as MONTHS, CLASSES
)

# School-month → calendar-month
_SCHOOL_CAL = {
    'Septembre': 9, 'Octobre': 10, 'Novembre': 11, 'Décembre': 12,
    'Janvier': 1, 'Février': 2, 'Mars': 3, 'Avril': 4, 'Mai': 5, 'Juin': 6,
}
_CAL_TO_SIDX = {9: 0, 10: 1, 11: 2, 12: 3, 1: 4, 2: 5, 3: 6, 4: 7, 5: 8, 6: 9}

# Month short labels for charts (aligned with SCHOOL_MONTHS order)
_SHORT = ['Sep', 'Oct', 'Nov', 'Déc', 'Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun']


def _current_school_month_name():
    cm = datetime.now().month
    idx = _CAL_TO_SIDX.get(cm)
    return SCHOOL_MONTHS[idx] if idx is not None else None


# ── Reusable widgets ──────────────────────────────────────────────────────────

def stat_card(icon, label, value, accent, accent_light, subtitle=None):
    card = QFrame()
    card.setObjectName('stat_card')
    card.setMinimumHeight(112)
    card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    card.setStyleSheet(f'''
        QFrame#stat_card {{
            background: {BG_CARD}; border: 1px solid {BORDER};
            border-radius: 14px; border-left: 4px solid {accent};
        }}
        QFrame#stat_card:hover {{ background: {accent_light}; }}
    ''')
    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 14, 18, 12)
    lay.setSpacing(6)

    top = QHBoxLayout()
    pill = QLabel(icon)
    pill.setFixedSize(36, 36)
    pill.setAlignment(Qt.AlignCenter)
    pill.setStyleSheet(f'background: {accent_light}; border-radius: 10px; font-size: 17px;')
    top.addWidget(pill)
    top.addStretch()

    val_lbl = QLabel(str(value))
    val_lbl.setStyleSheet(
        f'font-size: 22px; font-weight: 800; color: {accent}; background: transparent;'
    )
    top.addWidget(val_lbl)

    lbl = QLabel(label)
    lbl.setStyleSheet(
        f'font-size: 11px; font-weight: 600; color: {TEXT_SUB}; '
        f'letter-spacing: 0.3px; background: transparent;'
    )
    lay.addLayout(top)
    lay.addWidget(lbl)

    if subtitle:
        sub = QLabel(subtitle)
        sub.setStyleSheet('font-size: 10px; color: #9CA3AF; background: transparent;')
        sub.setWordWrap(True)
        lay.addWidget(sub)
        card._sub = sub
    else:
        card._sub = None

    card._val = val_lbl
    return card


def section_title(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f'color: {TEXT_MAIN}; font-size: 13px; font-weight: 700; '
        f'background: transparent; padding: 4px 0;'
    )
    return lbl


def divider():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f'color: {BORDER}; background: {BORDER}; max-height: 1px;')
    return line


# ── Dashboard Widget ──────────────────────────────────────────────────────────

class DashboardWidget(QWidget):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.setStyleSheet('background: transparent;')
        self._selected_month = None   # None = "current month"
        self._setup_ui()
        self._load_data()

    # ── UI skeleton ───────────────────────────────────────────────────────────
    def _setup_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet('QScrollArea { border: none; background: transparent; }')

        container = QWidget()
        container.setStyleSheet('background: transparent;')
        self.vl = QVBoxLayout(container)
        self.vl.setContentsMargins(28, 24, 28, 32)
        self.vl.setSpacing(20)

        # ── Top bar: greeting + month filter ─────────────────────────────────
        now = datetime.now()
        greeting = 'Bonjour' if now.hour < 12 else ('Bon après-midi' if now.hour < 18 else 'Bonsoir')

        top_bar = QHBoxLayout()
        top_bar.setSpacing(16)

        # Greeting block
        greet_col = QVBoxLayout(); greet_col.setSpacing(2)
        g = QLabel(f'{greeting} ☀️')
        g.setStyleSheet('color: #1A1D2E; font-size: 22px; font-weight: 800; background: transparent;')
        d = QLabel(now.strftime('%A %d %B %Y'))
        d.setStyleSheet('color: #9CA3AF; font-size: 12px; background: transparent;')
        greet_col.addWidget(g); greet_col.addWidget(d)
        top_bar.addLayout(greet_col)
        top_bar.addStretch()

        # Month filter pill
        filter_frame = QFrame()
        filter_frame.setStyleSheet(
            f'QFrame {{ background: {BG_CARD}; border: 1.5px solid {BORDER}; '
            f'border-radius: 12px; }}'
        )
        fl = QHBoxLayout(filter_frame)
        fl.setContentsMargins(14, 8, 14, 8)
        fl.setSpacing(10)

        filter_icon = QLabel('📅')
        filter_icon.setStyleSheet('font-size: 16px; background: transparent;')

        filter_lbl = QLabel('Afficher le mois :')
        filter_lbl.setStyleSheet(
            f'color: {TEXT_SUB}; font-size: 12px; font-weight: 600; background: transparent;'
        )

        combo_css = (
            f'QComboBox {{ background: {PRIMARY_LIGHT}; border: 1.5px solid {PRIMARY}33; '
            f'border-radius: 8px; color: {PRIMARY}; padding: 4px 12px; '
            f'font-size: 13px; font-weight: 700; min-width: 160px; }}'
            f'QComboBox::drop-down {{ border: none; width: 22px; }}'
            f'QComboBox QAbstractItemView {{ background: white; border: 1.5px solid {BORDER}; '
            f'border-radius: 8px; color: {TEXT_MAIN}; outline: none; }}'
            f'QComboBox QAbstractItemView::item {{ padding: 8px 14px; }}'
            f'QComboBox QAbstractItemView::item:selected {{ background: {PRIMARY_LIGHT}; color: {PRIMARY}; }}'
        )
        self.month_combo = QComboBox()
        self.month_combo.setStyleSheet(combo_css)
        self.month_combo.addItem('📍 Mois en cours', None)
        for month in SCHOOL_MONTHS:
            self.month_combo.addItem(month, month)
        self.month_combo.currentIndexChanged.connect(self._on_month_changed)

        reset_btn = QPushButton('↺')
        reset_btn.setFixedSize(32, 32)
        reset_btn.setToolTip('Revenir au mois en cours')
        reset_btn.setStyleSheet(
            f'QPushButton {{ background: {PRIMARY_LIGHT}; color: {PRIMARY}; border: none; '
            f'border-radius: 8px; font-size: 16px; font-weight: 700; }}'
            f'QPushButton:hover {{ background: {PRIMARY}; color: white; }}'
        )
        reset_btn.clicked.connect(self._reset_to_current)

        fl.addWidget(filter_icon)
        fl.addWidget(filter_lbl)
        fl.addWidget(self.month_combo)
        fl.addWidget(reset_btn)
        top_bar.addWidget(filter_frame)

        self.vl.addLayout(top_bar)

        # Selected month indicator banner
        self.month_banner = QFrame()
        self.month_banner.setVisible(False)   # hidden when showing current month
        self.month_banner.setStyleSheet(
            f'QFrame {{ background: {PRIMARY_LIGHT}; border: 1.5px solid {PRIMARY}44; '
            f'border-radius: 10px; }}'
        )
        bl = QHBoxLayout(self.month_banner)
        bl.setContentsMargins(16, 8, 16, 8)
        bl.setSpacing(10)
        self.banner_icon = QLabel('📅')
        self.banner_icon.setStyleSheet('font-size: 16px; background: transparent;')
        self.banner_lbl = QLabel('')
        self.banner_lbl.setStyleSheet(
            f'color: {PRIMARY}; font-size: 13px; font-weight: 700; background: transparent;'
        )
        bl.addWidget(self.banner_icon)
        bl.addWidget(self.banner_lbl)
        bl.addStretch()
        self.vl.addWidget(self.month_banner)

        # ── 1. Students ───────────────────────────────────────────────────────
        self.vl.addWidget(section_title('👤  Élèves'))
        self.sg = QGridLayout(); self.sg.setSpacing(12)
        self.vl.addLayout(self.sg)

        # ── 2. Revenue ────────────────────────────────────────────────────────
        self.vl.addWidget(divider())
        self.rev_title = section_title('💰  Revenus')
        self.vl.addWidget(self.rev_title)
        self.rg = QGridLayout(); self.rg.setSpacing(12)
        self.vl.addLayout(self.rg)

        # ── 3. Insurance ──────────────────────────────────────────────────────
        self.vl.addWidget(divider())
        self.vl.addWidget(section_title('🛡️  Assurances  (suivi séparé — hors bénéfice mensuel)'))
        self.ig = QGridLayout(); self.ig.setSpacing(12)
        self.vl.addLayout(self.ig)

        # ── 4. Expenses ───────────────────────────────────────────────────────
        self.vl.addWidget(divider())
        self.exp_title = section_title('💸  Dépenses')
        self.vl.addWidget(self.exp_title)
        self.eg = QGridLayout(); self.eg.setSpacing(12)
        self.vl.addLayout(self.eg)

        # ── 5. Salaries ───────────────────────────────────────────────────────
        self.vl.addWidget(divider())
        self.vl.addWidget(section_title('👔  Salaires'))
        self.salg = QGridLayout(); self.salg.setSpacing(12)
        self.vl.addLayout(self.salg)

        # ── 6. Monthly Profit ─────────────────────────────────────────────────
        self.vl.addWidget(divider())
        self.profit_title = section_title('📈  Bénéfice')
        self.vl.addWidget(self.profit_title)
        self.profit_row = QHBoxLayout(); self.profit_row.setSpacing(12)
        self.vl.addLayout(self.profit_row)

        # ── Re-inscription ────────────────────────────────────────────────────
        self.vl.addWidget(divider())
        self.vl.addWidget(section_title('🔄  Statut Ré-inscription'))
        reinsc_frame = QFrame()
        reinsc_frame.setStyleSheet(
            f'QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 14px; }}'
        )
        rfl = QVBoxLayout(reinsc_frame)
        rfl.setContentsMargins(20, 16, 20, 16); rfl.setSpacing(12)
        self.reinsc_row = QHBoxLayout(); self.reinsc_row.setSpacing(12)
        rfl.addLayout(self.reinsc_row)
        self.vl.addWidget(reinsc_frame)

        # ── Charts ────────────────────────────────────────────────────────────
        if HAS_MPL:
            self.vl.addWidget(divider())
            self.vl.addWidget(section_title('📊  Analytiques'))

            charts_row1 = QHBoxLayout(); charts_row1.setSpacing(16)
            self.profit_chart_frame, self.profit_chart_layout = self._chart_card(
                '📈  Bénéfice mensuel — Revenue + Transport − Dépenses − Salaires'
            )
            self.revexp_frame, self.revexp_layout = self._chart_card(
                '💰 vs 💸  Revenus vs Dépenses par mois'
            )
            charts_row1.addWidget(self.profit_chart_frame, 1)
            charts_row1.addWidget(self.revexp_frame, 1)
            self.vl.addLayout(charts_row1)

            charts_row2 = QHBoxLayout(); charts_row2.setSpacing(16)
            self.pay_rate_frame, self.pay_rate_layout = self._chart_card(
                '✅  Taux de paiement élèves par mois (NAN exclus)'
            )
            self.cls_frame, self.cls_layout = self._chart_card(
                '🎓  Répartition par classe'
            )
            charts_row2.addWidget(self.pay_rate_frame, 3)
            charts_row2.addWidget(self.cls_frame, 2)
            self.vl.addLayout(charts_row2)

        # ── Notifications ─────────────────────────────────────────────────────
        self.vl.addWidget(divider())
        notif_frame = QFrame()
        notif_frame.setStyleSheet(
            f'QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 14px; }}'
        )
        nfl = QVBoxLayout(notif_frame)
        nfl.setContentsMargins(20, 16, 20, 16); nfl.setSpacing(8)
        nt = QLabel('🔔  Alertes & Notifications')
        nt.setStyleSheet(f'color: {TEXT_MAIN}; font-size: 14px; font-weight: 700; background: transparent;')
        nfl.addWidget(nt)
        self.notif_inner = QVBoxLayout(); self.notif_inner.setSpacing(6)
        nfl.addLayout(self.notif_inner)
        self.vl.addWidget(notif_frame)
        self.vl.addStretch()

        scroll.setWidget(container)
        ol = QVBoxLayout(self)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.addWidget(scroll)

    # ── Month filter callbacks ────────────────────────────────────────────────

    def _on_month_changed(self, index):
        self._selected_month = self.month_combo.currentData()
        self._update_banner()
        self._load_data()

    def _reset_to_current(self):
        self.month_combo.setCurrentIndex(0)   # triggers _on_month_changed

    def _update_banner(self):
        if self._selected_month is None:
            self.month_banner.setVisible(False)
        else:
            self.month_banner.setVisible(True)
            self.banner_lbl.setText(
                f'Données filtrées pour : {self._selected_month}  '
                f'(cliquez sur ↺ pour revenir au mois en cours)'
            )

    def _resolve_month(self):
        """Return (month_name, calendar_year) for the selected or current month."""
        cy = datetime.now().year
        if self._selected_month:
            month_name = self._selected_month
            # Derive calendar year from school year setting
            sy = self._get_setting('school_year', '2024-25')
            try:
                end_year = int(sy.split('-')[0]) + 1
            except Exception:
                end_year = cy
            cal_month = _SCHOOL_CAL.get(month_name, 1)
            pay_year = (end_year - 1) if cal_month >= 9 else end_year
        else:
            month_name = _current_school_month_name()
            pay_year = cy
        return month_name, pay_year

    # ── Chart card helpers ────────────────────────────────────────────────────

    def _chart_card(self, title):
        frame = QFrame()
        frame.setStyleSheet(
            f'QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 14px; }}'
        )
        frame.setMinimumHeight(280)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16); layout.setSpacing(10)
        t = QLabel(title)
        t.setStyleSheet(f'color: {TEXT_MAIN}; font-size: 12px; font-weight: 700; background: transparent;')
        layout.addWidget(t)
        ph = QLabel('Chargement...')
        ph.setAlignment(Qt.AlignCenter)
        ph.setStyleSheet('color: #D1D5DB; font-size: 13px; background: transparent;')
        layout.addWidget(ph)
        frame._ph = ph
        return frame, layout

    def _clear_chart(self, frame, layout):
        if hasattr(frame, '_ph') and frame._ph:
            frame._ph.setParent(None)
            frame._ph = None
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), FigureCanvas):
                item.widget().setParent(None)

    def _clear_grid(self, grid):
        for i in reversed(range(grid.count())):
            item = grid.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_data(self):
        self.session.expire_all()
        try:
            self._compute_and_render()
        except Exception:
            import traceback; traceback.print_exc()
            self._render_zeroes()

    def _compute_and_render(self):
        now          = datetime.now()
        cy           = now.year
        cm           = now.month
        school_year  = self._get_setting('school_year', '2024-25')
        students     = self.session.query(Student).filter_by(active=True).all()
        student_ids  = {s.id: s for s in students}

        # Resolve selected month
        month_name, pay_year = self._resolve_month()

        # Update section labels
        month_label = month_name if month_name else '(hors période scolaire)'
        self.rev_title.setText(f'💰  Revenus — {month_label}')
        self.exp_title.setText(f'💸  Dépenses — {month_label}')
        self.profit_title.setText(f'📈  Bénéfice — {month_label}')

        # ── 1. STUDENTS ───────────────────────────────────────────────────────
        n_total = len(students)

        records_sel_month = {}
        if month_name:
            for r in self.session.query(MonthRecord).filter_by(
                month_name=month_name, school_year=school_year
            ).all():
                records_sel_month[r.student_id] = r

        # NAN students excluded from paid/unpaid
        n_paid = sum(
            1 for s in students
            if records_sel_month.get(s.id) and records_sel_month[s.id].status == 'paid'
        )
        n_unpaid = sum(
            1 for s in students
            if records_sel_month.get(s.id) and records_sel_month[s.id].status == 'unpaid'
        )

        # Outstanding = sum of all unpaid months (all year)
        all_unpaid = self.session.query(MonthRecord).filter_by(
            status='unpaid', school_year=school_year
        ).all()
        outstanding = sum(
            (student_ids[r.student_id].monthly_fee or 0.0) +
            ((student_ids[r.student_id].transport_fee or 0.0)
             if student_ids[r.student_id].has_transport else 0.0)
            for r in all_unpaid if r.student_id in student_ids
        )

        # ── 2. REVENUE (selected month) ───────────────────────────────────────
        expected_revenue = 0.0
        if month_name:
            for s in students:
                rec = records_sel_month.get(s.id)
                if rec and rec.status == 'nan':
                    continue
                expected_revenue += (s.monthly_fee or 0.0) + (
                    (s.transport_fee or 0.0) if s.has_transport else 0.0
                )

        collected_revenue = 0.0
        if month_name:
            for p in self.session.query(Payment).filter(
                Payment.payment_type.in_(['monthly', 'transport']),
                Payment.month == month_name,
                Payment.school_year == school_year,
            ).all():
                collected_revenue += p.amount or 0.0

        revenue_gap = max(0.0, expected_revenue - collected_revenue)

        # ── 3. INSURANCE (full school year, not month-filtered) ───────────────
        ins_payments = self.session.query(Payment).filter_by(
            payment_type='insurance', school_year=school_year
        ).all()
        insurance_collected = sum(p.amount or 0.0 for p in ins_payments)
        n_no_insurance = sum(1 for s in students if not s.insurance_paid)

        # ── 4. EXPENSES (selected month) ──────────────────────────────────────
        active_cats = self.session.query(ExpenseCategory).filter_by(active=True).all()
        expected_expenses = sum(c.monthly_amount or 0.0 for c in active_cats)

        paid_expenses = 0.0
        if month_name:
            for ep in self.session.query(ExpensePayment).filter_by(
                month=month_name, year=pay_year
            ).all():
                paid_expenses += ep.amount or 0.0

        remaining_expenses = max(0.0, expected_expenses - paid_expenses)

        # ── 5. SALARIES ───────────────────────────────────────────────────────
        n_employees = self.session.query(Employee).filter_by(active=True).count()

        # Salaries paid for selected month specifically
        paid_this_month_ids = set()
        sal_this_month = 0.0
        if month_name:
            for sal in self.session.query(Salary).filter_by(
                month=month_name, paid=True
            ).all():
                # Filter by school year range
                if sal.year == pay_year or (
                    _SCHOOL_CAL.get(month_name, 0) >= 9 and sal.year == pay_year
                ):
                    paid_this_month_ids.add(sal.employee_id)
                    sal_this_month += sal.net_salary or sal.total or 0.0

        salaries_paid_count = len(paid_this_month_ids)
        salaries_pending    = max(0, n_employees - salaries_paid_count)

        # Total salaries paid this full school year (for the card)
        try:
            sy_start = int(school_year.split('-')[0])
            sy_end   = sy_start + 1
        except Exception:
            sy_start, sy_end = cy - 1, cy

        total_salary_paid = sum(
            (s.net_salary or s.total or 0.0)
            for s in self.session.query(Salary).filter_by(paid=True).all()
            if s.year in (sy_start, sy_end)
        )

        # ── 6. PROFIT (selected month) ────────────────────────────────────────
        monthly_profit = collected_revenue - paid_expenses - sal_this_month

        # ── Re-inscription ────────────────────────────────────────────────────
        n_yes  = sum(1 for s in students if getattr(s, 'reinscription_status', 'pending') == 'yes')
        n_no   = sum(1 for s in students if getattr(s, 'reinscription_status', 'pending') == 'no')
        n_pend = sum(1 for s in students if getattr(s, 'reinscription_status', 'pending') == 'pending')

        # ── Render ────────────────────────────────────────────────────────────
        self._render_students(n_total, n_paid, n_unpaid, outstanding)
        self._render_revenue(expected_revenue, collected_revenue, revenue_gap)
        self._render_insurance(insurance_collected, n_no_insurance)
        self._render_expenses(expected_expenses, paid_expenses, remaining_expenses)
        self._render_salaries(n_employees, salaries_paid_count, salaries_pending, total_salary_paid)
        self._render_profit(monthly_profit, collected_revenue, paid_expenses, sal_this_month)
        self._render_reinscription(n_yes, n_no, n_pend)

        if HAS_MPL:
            # Determine highlight index for charts
            highlight_idx = None
            if month_name and month_name in SCHOOL_MONTHS:
                highlight_idx = SCHOOL_MONTHS.index(month_name)

            self._draw_monthly_profit(school_year, pay_year, highlight_idx)
            self._draw_rev_vs_exp(school_year, pay_year, highlight_idx)
            self._draw_payment_rate(school_year, highlight_idx)
            self._draw_classes()

        self._draw_notifications(n_no_insurance, n_unpaid, n_pend, outstanding)

    # ── KPI Renderers ─────────────────────────────────────────────────────────

    def _render_students(self, n_total, n_paid, n_unpaid, outstanding):
        self._clear_grid(self.sg)
        sel = self._selected_month or _current_school_month_name() or ''
        month_suffix = f' ({sel})' if sel else ''
        cards = [
            ('👥', 'Total élèves',                    n_total,                   PRIMARY,  PRIMARY_LIGHT),
            ('✅', f'Payés{month_suffix}',             n_paid,                    SUCCESS,  SUCCESS_LIGHT),
            ('⏳', f'Non payés{month_suffix}',         n_unpaid,                  DANGER,   DANGER_LIGHT),
            ('💳', 'Créances totales (toute l\'année)', f'{outstanding:,.0f} MAD', WARNING,  WARNING_LIGHT),
        ]
        for i, args in enumerate(cards):
            self.sg.addWidget(stat_card(*args), 0, i)

    def _render_revenue(self, expected, collected, gap):
        self._clear_grid(self.rg)
        cards = [
            ('📊', 'Revenus attendus',   f'{expected:,.0f} MAD',   PURPLE,  PURPLE_LIGHT),
            ('💰', 'Revenus encaissés',  f'{collected:,.0f} MAD',  SUCCESS, SUCCESS_LIGHT),
            ('📉', 'Écart de revenus',   f'{gap:,.0f} MAD',        DANGER,  DANGER_LIGHT),
        ]
        for i, args in enumerate(cards):
            self.rg.addWidget(stat_card(*args), 0, i)

    def _render_insurance(self, collected, n_no_ins):
        self._clear_grid(self.ig)
        cards = [
            ('🛡️', 'Assurances encaissées (année)',  f'{collected:,.0f} MAD', TEAL,    TEAL_LIGHT),
            ('❌',  'Sans assurance',                  n_no_ins,                WARNING, WARNING_LIGHT),
        ]
        for i, args in enumerate(cards):
            self.ig.addWidget(stat_card(*args), 0, i)

    def _render_expenses(self, expected, paid, remaining):
        self._clear_grid(self.eg)
        cards = [
            ('📋', 'Dépenses prévues',  f'{expected:,.0f} MAD',  INFO,    INFO_LIGHT),
            ('💸', 'Dépenses payées',   f'{paid:,.0f} MAD',      DANGER,  DANGER_LIGHT),
            ('🔖', 'Restant à payer',   f'{remaining:,.0f} MAD', WARNING, WARNING_LIGHT),
        ]
        for i, args in enumerate(cards):
            self.eg.addWidget(stat_card(*args), 0, i)

    def _render_salaries(self, n_emp, n_paid, n_pending, total_paid):
        self._clear_grid(self.salg)
        cards = [
            ('👔', 'Total employés',      n_emp,                    PRIMARY, PRIMARY_LIGHT),
            ('✅', 'Salaires versés',      n_paid,                   SUCCESS, SUCCESS_LIGHT),
            ('⏳', 'Salaires en attente',  n_pending,                DANGER,  DANGER_LIGHT),
            ('💰', 'Total versé (année)',  f'{total_paid:,.0f} MAD', PURPLE,  PURPLE_LIGHT),
        ]
        for i, args in enumerate(cards):
            self.salg.addWidget(stat_card(*args), 0, i)

    def _render_profit(self, profit, revenue, expenses, salaries):
        for i in reversed(range(self.profit_row.count())):
            w = self.profit_row.itemAt(i).widget()
            if w: w.setParent(None)

        color = SUCCESS if profit >= 0 else DANGER
        light = SUCCESS_LIGHT if profit >= 0 else DANGER_LIGHT
        sub   = (f'Revenus: {revenue:,.0f}  −  '
                 f'Dépenses: {expenses:,.0f}  −  '
                 f'Salaires: {salaries:,.0f}')
        self.profit_row.addWidget(
            stat_card('📈', 'Bénéfice du mois sélectionné',
                      f'{profit:,.0f} MAD', color, light, subtitle=sub)
        )

    def _render_reinscription(self, n_yes, n_no, n_pend):
        for i in reversed(range(self.reinsc_row.count())):
            w = self.reinsc_row.itemAt(i).widget()
            if w: w.setParent(None)
        for val, count, color, light in [
            ('yes',     n_yes,  SUCCESS, SUCCESS_LIGHT),
            ('no',      n_no,   DANGER,  DANGER_LIGHT),
            ('pending', n_pend, WARNING, WARNING_LIGHT),
        ]:
            card = QFrame()
            card.setStyleSheet(
                f'QFrame {{ background: {light}; border: 1px solid {color}33; '
                f'border-radius: 12px; border-left: 4px solid {color}; }}'
            )
            card.setFixedHeight(70)
            ccl = QVBoxLayout(card)
            ccl.setContentsMargins(16, 10, 16, 10); ccl.setSpacing(3)
            QLabel.__init__  # silence lint
            vl2 = QLabel(str(count))
            vl2.setStyleSheet(f'color: {color}; font-size: 20px; font-weight: 800; background: transparent;')
            ll2 = QLabel(REINSCRIPTION_LABELS.get(val, val))
            ll2.setStyleSheet(f'color: {TEXT_SUB}; font-size: 11px; font-weight: 500; background: transparent;')
            ccl.addWidget(vl2); ccl.addWidget(ll2)
            self.reinsc_row.addWidget(card)
        self.reinsc_row.addStretch()

    def _render_zeroes(self):
        self._render_students(0, 0, 0, 0.0)
        self._render_revenue(0.0, 0.0, 0.0)
        self._render_insurance(0.0, 0)
        self._render_expenses(0.0, 0.0, 0.0)
        self._render_salaries(0, 0, 0, 0.0)
        self._render_profit(0.0, 0.0, 0.0, 0.0)
        self._render_reinscription(0, 0, 0)

    # ── Chart data helpers ────────────────────────────────────────────────────

    def _school_month_revenue(self, school_year):
        result = [0.0] * 10
        for p in self.session.query(Payment).filter(
            Payment.payment_type.in_(['monthly', 'transport']),
            Payment.school_year == school_year,
        ).all():
            try:
                idx = SCHOOL_MONTHS.index(p.month)
                result[idx] += p.amount or 0.0
            except (ValueError, TypeError):
                pass
        return result

    def _school_month_expenses(self, pay_year):
        result = [0.0] * 10
        prev_year = pay_year - 1
        for ep in self.session.query(ExpensePayment).all():
            try:
                idx = SCHOOL_MONTHS.index(ep.month)
                # Sep-Dec → prev_year, Jan-Jun → pay_year
                expected_yr = prev_year if idx <= 3 else pay_year
                if ep.year == expected_yr:
                    result[idx] += ep.amount or 0.0
            except (ValueError, TypeError):
                pass
        return result

    def _school_month_salaries(self):
        result = [0.0] * 10
        for sal in self.session.query(Salary).filter_by(paid=True).all():
            try:
                idx = SCHOOL_MONTHS.index(sal.month)
                result[idx] += sal.net_salary or sal.total or 0.0
            except (ValueError, TypeError):
                pass
        return result

    # ── Charts ────────────────────────────────────────────────────────────────

    def _apply_highlight(self, ax, highlight_idx, bars_or_lines, chart_type='bar'):
        """Dim all bars/lines except the selected month."""
        if highlight_idx is None:
            return
        if chart_type == 'bar':
            for i, bar in enumerate(bars_or_lines):
                bar.set_alpha(1.0 if i == highlight_idx else 0.25)

    def _draw_monthly_profit(self, school_year, pay_year, highlight_idx):
        self._clear_chart(self.profit_chart_frame, self.profit_chart_layout)
        rev    = self._school_month_revenue(school_year)
        exp    = self._school_month_expenses(pay_year)
        sal    = self._school_month_salaries()
        profit = [rev[i] - exp[i] - sal[i] for i in range(10)]

        bar_colors = [f'#{SUCCESS[1:]}' if v >= 0 else f'#{DANGER[1:]}' for v in profit]

        fig = Figure(figsize=(7, 3.2), facecolor='white')
        ax  = fig.add_subplot(111)
        ax.set_facecolor('white')

        bars = ax.bar(range(10), profit, color=bar_colors, width=0.6, zorder=3)
        ax.axhline(0, color='#E5E7EB', linewidth=1, zorder=2)

        # Highlight selected month
        if highlight_idx is not None:
            for i, bar in enumerate(bars):
                if i != highlight_idx:
                    bar.set_alpha(0.22)
            # Add value label on highlighted bar
            val = profit[highlight_idx]
            ax.annotate(
                f'{val:,.0f}',
                xy=(highlight_idx, val),
                xytext=(0, 6 if val >= 0 else -14),
                textcoords='offset points',
                ha='center', fontsize=8, fontweight='bold',
                color='#059669' if val >= 0 else '#DC2626',
            )

        ax.set_xticks(range(10))
        tick_colors = [
            PRIMARY if i == highlight_idx else '#9CA3AF'
            for i in range(10)
        ]
        labels = _SHORT[:]
        ax.set_xticklabels(labels, fontsize=8)
        for tick, color in zip(ax.get_xticklabels(), tick_colors):
            tick.set_color(color)
            if color == PRIMARY:
                tick.set_fontweight('bold')

        ax.yaxis.set_tick_params(labelcolor='#9CA3AF', labelsize=8)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.yaxis.grid(True, color='#F3F4F8', linewidth=1, zorder=0)
        ax.set_axisbelow(True)
        fig.tight_layout(pad=1.5)
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet('background: white;')
        self.profit_chart_layout.addWidget(canvas)

    def _draw_rev_vs_exp(self, school_year, pay_year, highlight_idx):
        self._clear_chart(self.revexp_frame, self.revexp_layout)
        rev = self._school_month_revenue(school_year)
        exp = self._school_month_expenses(pay_year)
        xs  = range(10)

        fig = Figure(figsize=(7, 3.2), facecolor='white')
        ax  = fig.add_subplot(111)
        ax.set_facecolor('white')

        ax.fill_between(xs, rev, alpha=0.10, color='#10B981')
        ax.fill_between(xs, exp, alpha=0.10, color='#EF4444')
        l1, = ax.plot(xs, rev, color='#10B981', linewidth=2.5, marker='o',
                      markersize=5, markerfacecolor='white', markeredgewidth=2, label='Revenus')
        l2, = ax.plot(xs, exp, color='#EF4444', linewidth=2.5, marker='o',
                      markersize=5, markerfacecolor='white', markeredgewidth=2, label='Dépenses')

        # Highlight selected month: draw bold vertical line + annotate
        if highlight_idx is not None:
            ax.axvline(highlight_idx, color=PRIMARY, linewidth=1.5, linestyle='--', alpha=0.5, zorder=1)
            ax.scatter([highlight_idx], [rev[highlight_idx]],
                       s=80, color='#10B981', zorder=5)
            ax.scatter([highlight_idx], [exp[highlight_idx]],
                       s=80, color='#EF4444', zorder=5)
            ax.annotate(
                f'Rev: {rev[highlight_idx]:,.0f}',
                xy=(highlight_idx, rev[highlight_idx]),
                xytext=(8, 4), textcoords='offset points',
                fontsize=7, color='#10B981', fontweight='bold',
            )
            ax.annotate(
                f'Dep: {exp[highlight_idx]:,.0f}',
                xy=(highlight_idx, exp[highlight_idx]),
                xytext=(8, -12), textcoords='offset points',
                fontsize=7, color='#EF4444', fontweight='bold',
            )

        ax.set_xticks(list(xs))
        labels = _SHORT[:]
        ax.set_xticklabels(labels, fontsize=8)
        tick_colors = [PRIMARY if i == highlight_idx else '#9CA3AF' for i in range(10)]
        for tick, color in zip(ax.get_xticklabels(), tick_colors):
            tick.set_color(color)
            if color == PRIMARY: tick.set_fontweight('bold')

        ax.yaxis.set_tick_params(labelcolor='#9CA3AF', labelsize=8)
        ax.legend(fontsize=8, frameon=False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.yaxis.grid(True, color='#F3F4F8', linewidth=1)
        ax.set_axisbelow(True)
        fig.tight_layout(pad=1.5)
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet('background: white;')
        self.revexp_layout.addWidget(canvas)

    def _draw_payment_rate(self, school_year, highlight_idx):
        self._clear_chart(self.pay_rate_frame, self.pay_rate_layout)
        paid_pct, unpaid_pct = [], []
        for month in SCHOOL_MONTHS:
            records = self.session.query(MonthRecord).filter_by(
                month_name=month, school_year=school_year
            ).all()
            active = [r for r in records if r.status != 'nan']
            total  = len(active)
            if total:
                p = sum(1 for r in active if r.status == 'paid')
                paid_pct.append(100.0 * p / total)
                unpaid_pct.append(100.0 * (total - p) / total)
            else:
                paid_pct.append(0.0)
                unpaid_pct.append(0.0)

        xs = range(len(SCHOOL_MONTHS))
        w  = 0.38

        fig = Figure(figsize=(8, 3.2), facecolor='white')
        ax  = fig.add_subplot(111)
        ax.set_facecolor('white')

        bars_p = ax.bar([x - w / 2 for x in xs], paid_pct,   width=w,
                        color='#10B981', alpha=0.85, label='% Payés',   zorder=3)
        bars_u = ax.bar([x + w / 2 for x in xs], unpaid_pct, width=w,
                        color='#EF4444', alpha=0.85, label='% Impayés', zorder=3)

        if highlight_idx is not None:
            for i, (bp, bu) in enumerate(zip(bars_p, bars_u)):
                if i != highlight_idx:
                    bp.set_alpha(0.22)
                    bu.set_alpha(0.22)
            # Annotate highlighted bars
            ax.text(
                highlight_idx - w / 2, paid_pct[highlight_idx] + 2,
                f'{paid_pct[highlight_idx]:.0f}%',
                ha='center', fontsize=8, fontweight='bold', color='#10B981'
            )
            ax.text(
                highlight_idx + w / 2, unpaid_pct[highlight_idx] + 2,
                f'{unpaid_pct[highlight_idx]:.0f}%',
                ha='center', fontsize=8, fontweight='bold', color='#EF4444'
            )

        ax.set_xticks(list(xs))
        labels = _SHORT[:]
        ax.set_xticklabels(labels, fontsize=8)
        tick_colors = [PRIMARY if i == highlight_idx else '#9CA3AF' for i in range(10)]
        for tick, color in zip(ax.get_xticklabels(), tick_colors):
            tick.set_color(color)
            if color == PRIMARY: tick.set_fontweight('bold')

        ax.yaxis.set_tick_params(labelcolor='#9CA3AF', labelsize=8)
        ax.set_ylim(0, 115)
        ax.legend(fontsize=8, frameon=False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.yaxis.grid(True, color='#F3F4F8', linewidth=1, zorder=0)
        ax.set_axisbelow(True)
        fig.tight_layout(pad=1.5)
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet('background: white;')
        self.pay_rate_layout.addWidget(canvas)

    def _draw_classes(self):
        self._clear_chart(self.cls_frame, self.cls_layout)
        counts, labels = [], []
        for cls in CLASSES:
            c = self.session.query(Student).filter_by(class_name=cls, active=True).count()
            if c > 0:
                counts.append(c); labels.append(cls)
        if not counts:
            counts, labels = [1], ['Aucun']

        fig = Figure(figsize=(4, 3), facecolor='white')
        ax  = fig.add_subplot(111)
        palette = ['#4F46E5','#10B981','#F59E0B','#EF4444','#8B5CF6','#14B8A6',
                   '#EC4899','#3B82F6','#6D28D9','#059669','#D97706','#DC2626',
                   '#7C3AED','#0D9488','#BE185D','#1D4ED8']
        ax.pie(counts, labels=labels, autopct='%1.0f%%',
               colors=palette[:len(counts)],
               textprops={'fontsize': 8, 'color': '#374151'},
               pctdistance=0.82,
               wedgeprops={'linewidth': 2, 'edgecolor': 'white'})
        fig.tight_layout(pad=0.5)
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet('background: white;')
        self.cls_layout.addWidget(canvas)

    # ── Notifications ─────────────────────────────────────────────────────────

    def _draw_notifications(self, no_ins, unpaid_this_month, reinsc_pend, outstanding):
        for i in reversed(range(self.notif_inner.count())):
            w = self.notif_inner.itemAt(i).widget()
            if w: w.setParent(None)

        sel = self._selected_month or _current_school_month_name() or ''
        notifs = []
        if no_ins:
            notifs.append(('⚠️', f'{no_ins} élèves sans assurance payée', WARNING, WARNING_LIGHT))
        if unpaid_this_month:
            suffix = f' — {sel}' if sel else ''
            notifs.append(('💳', f'{unpaid_this_month} élèves non payés{suffix}', DANGER, DANGER_LIGHT))
        if outstanding > 0:
            notifs.append(('📋', f'Créances totales: {outstanding:,.0f} MAD', DANGER, DANGER_LIGHT))
        if reinsc_pend:
            notifs.append(('🔄', f'{reinsc_pend} ré-inscriptions en attente', WARNING, WARNING_LIGHT))
        if not notifs:
            notifs.append(('✅', 'Tout est en ordre — bonne journée !', SUCCESS, SUCCESS_LIGHT))

        for icon, msg, color, light in notifs:
            row = QFrame()
            row.setStyleSheet(
                f'QFrame {{ background: {light}; border-radius: 10px; border-left: 3px solid {color}; }}'
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(14, 8, 14, 8); rl.setSpacing(10)
            il = QLabel(icon)
            il.setStyleSheet('font-size: 15px; background: transparent;')
            ml = QLabel(msg)
            ml.setStyleSheet(f'color: {TEXT_MAIN}; font-size: 12px; font-weight: 500; background: transparent;')
            rl.addWidget(il); rl.addWidget(ml); rl.addStretch()
            self.notif_inner.addWidget(row)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_setting(self, key, default=''):
        s = self.session.query(Setting).filter_by(key=key).first()
        return s.value if s else default

    def refresh(self):
        self._load_data()
