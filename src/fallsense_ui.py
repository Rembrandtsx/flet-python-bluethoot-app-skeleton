"""FallSense prototype UI (login → perfil → monitor → alerta simulada)."""

from __future__ import annotations

import flet as ft

# —— Palette (Figma-inspired) ——
C_WHITE = "#FFFFFF"
C_BLUE = "#1976D2"
C_BLUE_DARK = "#0D47A1"
C_TEAL_LIGHT = "#26A69A"
C_GREY = "#546E7A"
C_GREY_LIGHT = "#78909C"
C_GREY_400 = "#BDBDBD"
C_GREY_700 = "#616161"
C_BORDER = "#E3F2FD"
C_GREEN = "#2E7D32"
C_GREEN_LIGHT = "#A5D6A7"
C_RED_ALERT = "#E53935"
C_CYAN_BG = "#E0F7F9"
C_CYAN_BORDER = "#4DD0E1"
C_CYAN_TEXT = "#006064"
C_PAGE_BG = "#F5F7FA"
C_TEAL = "#00897B"

# Bundled under app `assets/` (see `src/assets/Logo.png`).
LOGO_ASSET = "Logo.png"

CONDITIONS = [
    "Alzheimer",
    "Parkinson",
    "Esclerosis Múltiple",
    "Epilepsia",
    "Demencia Vascular",
    "Ataxia",
    "Otra condición neurológica",
]


def is_valid_email(value: str) -> bool:
    s = (value or "").strip()
    if "@" not in s or s.count("@") != 1:
        return False
    local, domain = s.split("@", 1)
    if not local or not domain or "." not in domain:
        return False
    if any(c.isspace() for c in s):
        return False
    return True


def _gradient_cta(text: str, on_click) -> ft.Control:
    return ft.Container(
        on_click=on_click,
        border_radius=28,
        padding=ft.padding.symmetric(horizontal=28, vertical=16),
        gradient=ft.LinearGradient(
            colors=[C_TEAL_LIGHT, C_BLUE],
            begin=ft.Alignment.CENTER_LEFT,
            end=ft.Alignment.CENTER_RIGHT,
        ),
        content=ft.Text(
            text,
            size=17,
            weight=ft.FontWeight.W_600,
            color=C_WHITE,
            text_align=ft.TextAlign.CENTER,
        ),
        alignment=ft.Alignment.CENTER,
    )


def logo_block(compact: bool = False) -> ft.Control:
    """Brand mark (`Logo.png` includes brain icon + FallSense wordmark)."""
    width = 180.0 if compact else 240.0
    return ft.Column(
        [
            ft.Image(
                src=LOGO_ASSET,
                width=width,
                fit=ft.BoxFit.CONTAIN,
                error_content=ft.Column(
                    [
                        ft.Icon(ft.Icons.PSYCHOLOGY_ALT, size=48, color=C_TEAL),
                        ft.Text(
                            "FallSense",
                            size=20,
                            weight=ft.FontWeight.W_700,
                            color=C_BLUE_DARK,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                    tight=True,
                ),
            ),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=4,
    )


def screen_login(
    email: ft.TextField,
    password: ft.TextField,
    err: ft.Text,
    on_login,
    on_register,
) -> ft.Control:
    return ft.Container(
        expand=True,
        bgcolor=C_WHITE,
        padding=ft.padding.symmetric(horizontal=28, vertical=32),
        content=ft.Column(
            [
                logo_block(),
                ft.Container(height=28),
                ft.Text(
                    "Inicia sesión para continuar",
                    size=16,
                    color=C_BLUE,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=32),
                ft.Text("Correo electrónico", size=14, color=C_BLUE, weight=ft.FontWeight.W_500),
                email,
                ft.Container(height=16),
                ft.Text("Contraseña", size=14, color=C_BLUE, weight=ft.FontWeight.W_500),
                password,
                err,
                ft.Container(height=28),
                _gradient_cta("Iniciar sesión", on_login),
                ft.Container(height=24),
                ft.TextButton(
                    content=ft.Text(
                        "¿No tienes cuenta? Regístrate",
                        color=C_TEAL,
                        weight=ft.FontWeight.W_500,
                    ),
                    on_click=on_register,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def screen_condition(
    option_buttons: list[ft.Control],
    err: ft.Text,
    on_continue,
) -> ft.Control:
    return ft.Container(
        expand=True,
        bgcolor=C_PAGE_BG,
        padding=ft.padding.symmetric(horizontal=20, vertical=24),
        content=ft.Column(
            [
                logo_block(compact=True),
                ft.Container(height=20),
                ft.Text(
                    "Información del Paciente",
                    size=22,
                    weight=ft.FontWeight.W_700,
                    color=C_BLUE_DARK,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=8),
                ft.Text(
                    "Selecciona la condición neurológica que padece tu familiar",
                    size=14,
                    color=C_BLUE,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=20),
                ft.Container(
                    padding=ft.padding.all(16),
                    bgcolor=C_WHITE,
                    border_radius=16,
                    shadow=ft.BoxShadow(
                        blur_radius=12,
                        color="#15000000",
                        offset=ft.Offset(0, 4),
                    ),
                    content=ft.Column(option_buttons, spacing=10),
                ),
                err,
                ft.Container(height=24),
                _gradient_cta("Continuar", on_continue),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def screen_home_shell(
    header: ft.Control,
    connection_card: ft.Control,
    vitals_card: ft.Control,
    chart_block: ft.Control,
    debug_block: ft.Control,
) -> ft.Control:
    return ft.Container(
        expand=True,
        bgcolor=C_PAGE_BG,
        padding=ft.padding.symmetric(horizontal=16, vertical=20),
        content=ft.Column(
            [
                header,
                ft.Container(height=16),
                connection_card,
                ft.Container(height=12),
                vitals_card,
                ft.Container(height=12),
                chart_block,
                ft.Container(height=8),
                debug_block,
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=0,
        ),
    )


def card(title: str, child: ft.Control) -> ft.Control:
    return ft.Container(
        padding=ft.padding.all(16),
        bgcolor=C_WHITE,
        border_radius=16,
        border=ft.border.all(1, C_BORDER),
        content=ft.Column(
            [
                ft.Text(title, size=13, weight=ft.FontWeight.W_600, color=C_GREY),
                ft.Container(height=10),
                child,
            ],
            spacing=0,
            tight=True,
        ),
    )


def screen_crisis(
    timer_text: ft.Text,
    on_cancel,
) -> ft.Control:
    return ft.Container(
        expand=True,
        bgcolor=C_PAGE_BG,
        padding=ft.padding.symmetric(horizontal=20, vertical=24),
        content=ft.Column(
            [
                logo_block(compact=True),
                ft.Container(height=20),
                ft.Container(
                    padding=ft.padding.all(18),
                    border_radius=16,
                    gradient=ft.LinearGradient(
                        colors=[C_TEAL, C_BLUE],
                        begin=ft.Alignment.TOP_LEFT,
                        end=ft.Alignment.BOTTOM_RIGHT,
                    ),
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=C_WHITE, size=36),
                            ft.Container(width=12),
                            ft.Column(
                                [
                                    ft.Text(
                                        "Posible episodio detectado",
                                        size=18,
                                        weight=ft.FontWeight.W_700,
                                        color=C_WHITE,
                                    ),
                                    ft.Text(
                                        "Nuestro sistema detectó un posible evento (simulación con sensor). "
                                        "¿Te encuentras bien?",
                                        size=14,
                                        color=C_WHITE,
                                        opacity=0.95,
                                    ),
                                ],
                                spacing=8,
                                expand=True,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                ),
                ft.Container(height=20),
                ft.Container(
                    padding=ft.padding.all(20),
                    bgcolor=C_WHITE,
                    border_radius=16,
                    content=ft.Column(
                        [
                            ft.Text(
                                "Si no confirmas que estás bien, se alertará a tus contactos en:",
                                size=14,
                                color=C_GREY,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Container(height=12),
                            timer_text,
                            ft.Text(
                                "minutos restantes",
                                size=13,
                                color=C_GREY_LIGHT,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),
                ft.Container(height=20),
                ft.Container(
                    on_click=on_cancel,
                    border_radius=28,
                    bgcolor=C_GREEN,
                    padding=ft.padding.symmetric(horizontal=20, vertical=16),
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=C_WHITE),
                            ft.Container(width=10),
                            ft.Text(
                                "Estoy bien — cancelar alerta",
                                size=16,
                                weight=ft.FontWeight.W_700,
                                color=C_WHITE,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ),
                ft.Container(height=16),
                ft.Container(
                    padding=ft.padding.all(14),
                    bgcolor=C_WHITE,
                    border_radius=12,
                    content=ft.Text(
                        "Si necesitas ayuda, no pulses el botón. Los contactos recibirán una alerta al finalizar la cuenta atrás (simulado).",
                        size=12,
                        color=C_GREY,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def screen_resolved(on_continue_home) -> ft.Control:
    return ft.Container(
        expand=True,
        bgcolor=C_WHITE,
        padding=ft.padding.symmetric(horizontal=28, vertical=48),
        content=ft.Column(
            [
                ft.Container(
                    width=88,
                    height=88,
                    border_radius=44,
                    bgcolor=C_GREEN_LIGHT,
                    border=ft.border.all(3, C_GREEN),
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(ft.Icons.CHECK, size=48, color=C_GREEN),
                ),
                ft.Container(height=28),
                ft.Text(
                    "¡Nos alegra que estés bien!",
                    size=24,
                    weight=ft.FontWeight.W_700,
                    color=C_BLUE_DARK,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=14),
                ft.Text(
                    "La alerta ha sido cancelada. Tus contactos no serán notificados.",
                    size=15,
                    color=C_GREY,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=24),
                ft.Container(
                    padding=ft.padding.all(16),
                    bgcolor=C_CYAN_BG,
                    border_radius=12,
                    border=ft.border.all(1, C_CYAN_BORDER),
                    content=ft.Text(
                        "Continuaremos monitoreando tu actividad para tu seguridad.",
                        size=14,
                        color=C_CYAN_TEXT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ),
                ft.Container(height=36),
                _gradient_cta("Volver al monitor", on_continue_home),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def styled_email_field() -> ft.TextField:
    return ft.TextField(
        hint_text="tu@email.com",
        border_radius=14,
        border_color=C_BORDER,
        focused_border_color=C_TEAL,
        cursor_color=C_TEAL,
    )


def styled_password_field() -> ft.TextField:
    return ft.TextField(
        hint_text="••••••••",
        password=True,
        can_reveal_password=True,
        border_radius=14,
        border_color=C_BORDER,
        focused_border_color=C_TEAL,
        cursor_color=C_TEAL,
    )
