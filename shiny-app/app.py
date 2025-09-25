from __future__ import annotations

import polars as pl

from great_tables import GT, html
import gt_extras as gte

from shiny import reactive
from shiny.express import input, render, ui
from pathlib import Path

APP_DIR = Path(__file__).parent

DATA_PATH = APP_DIR / "data" / "MLB2020-2024GameInfo.csv"


# --- Utility functions ---
def gt_plt_split_bar(
    gt: GT,
    columns: tuple[str, str],
    fill_left: str = "red",
    fill_right: str = "darkgreen",
    bar_height: float = 20,
    height: float = 30,
    width: float = 100,
    stroke_color: str | None = None,
    show_labels: bool = True,
    label_color: str = "white",
    domain: tuple[list[int | float], list[int | float]] | None = None,
) -> GT:
    if bar_height > height:
        bar_height = height
    if bar_height < 0:
        bar_height = 0
    if stroke_color is None:
        stroke_color = "transparent"

    col_left, col_right = columns
    vals_left = gt._tbl_data[col_left]
    vals_right = gt._tbl_data[col_right]
    domain_left = domain[0] if domain else [0, 1.5]
    domain_right = domain[1] if domain else [0, 7.5]

    def scale(val, domain):
        min_v, max_v = domain
        if max_v == min_v:
            return 0.5 * width
        return ((val - min_v) / (max_v - min_v)) * (width / 2)

    def make_split_bar(val_left, val_right):
        left_w = scale(val_left, domain_left)
        right_w = scale(val_right, domain_right)

        svg = f'''
        <svg width="{width}" height="{height}">
            <rect x="{width / 2 - left_w}" y="{(height - bar_height) / 2}" width="{left_w}" height="{bar_height}" fill="{fill_left}" stroke="{stroke_color}" />
            <rect x="{width / 2}" y="{(height - bar_height) / 2}" width="{right_w}" height="{bar_height}" fill="{fill_right}" stroke="{stroke_color}" />
            <line x1="{width / 2}" y1="0" x2="{width / 2}" y2="{height}" stroke="{stroke_color}" stroke-width="2"/>
            {'<text x="%d" y="%d" fill="%s" font-size="12" text-anchor="start" alignment-baseline="middle">%s</text>' % (width / 2 - left_w + 5, height / 2, label_color, val_left) if show_labels else ""}
            {'<text x="%d" y="%d" fill="%s" font-size="12" text-anchor="end" alignment-baseline="middle">%s</text>' % (width / 2 + right_w - 5, height / 2, label_color, val_right) if show_labels else ""}
        </svg>
        '''
        return f'<div style="display: flex;">{svg}</div>'

    for i, (v_left, v_right) in enumerate(zip(vals_left, vals_right)):
        gt = gt.fmt(
            lambda _vl=None, _vr=None, v_left=v_left, v_right=v_right: make_split_bar(
                v_left, v_right
            ),
            columns=col_left,
            rows=[i],
        )
    return gt


# --- Data loading ---
@reactive.calc
def pitcher_data():
    YEAR = int(input.year())
    prepend = YEAR * 10000

    df = pl.read_csv(str(DATA_PATH), ignore_errors=True)
    df = df.filter(
        (pl.col("Date") >= (prepend + 101)) & (pl.col("Date") <= (prepend + 1231))
    )

    pitcher_games = (
        df.select(
            [
                pl.col("VT").alias("Team"),
                pl.col("VT Starting Pitcher Name").alias("Starting Pitcher"),
                pl.col("VT Starting Pitcher ID").alias("Starting Pitcher ID"),
                pl.col("Winning Pitcher Name").alias("Winning Pitcher"),
                pl.col("Losing Pitcher Name").alias("Losing Pitcher"),
                pl.col("Winning Pitcher ID").alias("Winning Pitcher ID"),
                pl.col("Losing Pitcher ID").alias("Losing Pitcher ID"),
                pl.col("VT Score").alias("Team Runs"),
                pl.col("VT Errors").alias("Team Errors"),
            ]
        )
        .vstack(
            df.select(
                [
                    pl.col("HT").alias("Team"),
                    pl.col("HT Starting Pitcher Name").alias("Starting Pitcher"),
                    pl.col("HT Starting Pitcher ID").alias("Starting Pitcher ID"),
                    pl.col("Winning Pitcher Name").alias("Winning Pitcher"),
                    pl.col("Losing Pitcher Name").alias("Losing Pitcher"),
                    pl.col("Winning Pitcher ID").alias("Winning Pitcher ID"),
                    pl.col("Losing Pitcher ID").alias("Losing Pitcher ID"),
                    pl.col("HT Score").alias("Team Runs"),
                    pl.col("VT Errors").alias("Team Errors"),
                ]
            )
        )
        .filter(pl.col("Starting Pitcher").is_not_null())
    )

    pitcher_games = pitcher_games.with_columns(
        pl.when(pl.col("Starting Pitcher ID") == pl.col("Winning Pitcher ID"))
        .then(1)
        .when(pl.col("Starting Pitcher ID") == pl.col("Losing Pitcher ID"))
        .then(0)
        .otherwise(0.5)
        .alias("WinLoss")
    )

    pitcher_counts = (
        pitcher_games.group_by(["Team", "Starting Pitcher ID"])
        .agg(
            [
                pl.len().alias("Games Started"),
                (pl.col("Starting Pitcher ID") == pl.col("Winning Pitcher ID"))
                .sum()
                .alias("Wins"),
                (pl.col("Starting Pitcher ID") == pl.col("Losing Pitcher ID"))
                .sum()
                .alias("Losses"),
                pl.col("WinLoss"),
                pl.col("Starting Pitcher").first(),
                pl.col("Team Runs").mean().round(1),
                pl.col("Team Errors").mean().round(1),
            ]
        )
        .with_columns(
            pl.col("Team").map_elements(
                lambda t: str(APP_DIR / "data" / "images" / f"{t}.png")
            ).alias("Logo")
        )
    )

    top_pitchers = (
        pitcher_counts.sort(
            ["Games Started", "Starting Pitcher ID"], descending=[True, False]
        )
        .group_by("Team")
        .head(5)
        .sort(["Team", "Games Started"], descending=[False, True])
        .with_columns(
            pl.col("Starting Pitcher ID")
            .map_elements(
                lambda x: str(APP_DIR / "data" / "player_headshots_id" / f"{x}.png"),
                return_dtype=pl.Utf8
            )
            .alias("headshot_img")
        )
        .with_columns(
            (
                pl.col("Wins").cast(pl.Int64).cast(pl.Utf8)
                + "-"
                + pl.col("Losses").cast(pl.Int64).cast(pl.Utf8)
            ).alias("Record")
        )
    )

    top_pitchers = (
        top_pitchers.sort("Games Started", descending=True)
        .group_by("Starting Pitcher ID")
        .head(1)
    )

    era_df = pl.read_csv(str(APP_DIR / "data" / f"{YEAR}era.csv"), ignore_errors=True)

    top_pitchers_with_era = top_pitchers.join(
        era_df.select([pl.col("key_retro"), pl.col("ERA")]),
        left_on="Starting Pitcher ID",
        right_on="key_retro",
        how="left",
    )

    return top_pitchers_with_era


@reactive.calc
def team_choices():
    return sorted(pitcher_data()["Team"].unique().to_list())


# --- Shiny UI ---
ui.page_opts(title="MLB Pitchers Dashboard: Great Tables Contest 2025", fillable=True)

with ui.sidebar(title="Sort and Filter"):
    sort_choices = {
        "Wins": "Wins",
        "Games Started": "Games Started",
        "Team Runs": "Run Support",
        "ERA": "ERA",
        "Team Errors": "Team Errors",
    }
    ui.input_select(
        "sort_col",
        "Sort by",
        choices=sort_choices,
        selected="Wins",
    )
    ui.input_switch(
        "descending",
        "Descending",
        value=True,
    )
    ui.input_switch(
        "show_all",
        "Show all",
        value=False,
    )
    ui.input_select(
        "year",
        "Year",
        choices=["2022", "2023", "2024"],
        selected="2024",
    )

    @render.ui
    def team_selector():
        teams = team_choices()
        display_choices = {team: MLB_TEAM_ABBREVIATIONS.get(team, team) for team in teams}
        sorted_display_choices = dict(sorted(display_choices.items(), key=lambda item: item[1]))
        return ui.TagList(
            ui.input_select(
                "teams",
                "Teams",
                choices=sorted_display_choices,
                selected=teams,
                multiple=True,
                size=10,
            ),
            ui.p("Tip: Select all with ⌘A, or select one or more teams with ⌘-click.", style="font-size: 0.9em; color: #555; margin-top: 4px;")
        )

with ui.card(full_screen=True):

    @render.ui
    def gt_table():
        source_note_md = """
            <div style="margin-top:10px;">
            Luck is defined here as a combination of a pitcher's own 
            <span style="color:red;font-weight:bold;">team errors</span> 
            and 
            <span style="color:darkgreen;font-weight:bold;">run support</span> 
            received during their starts.
            <a href="https://github.com/juleswg23/baseball" target="_blank">View source code on GitHub</a>
            </div>
        """

        sort_col = input.sort_col()
        descending = input.descending()
        selected_teams = input.teams()
        show_all = input.show_all()
        data = pitcher_data()
        if selected_teams:
            data = data.filter(pl.col("Team").is_in(selected_teams))
        filt = data.sort(sort_col, descending=descending)
        if not show_all:
            filt = filt.head(14)
        gt = (
            GT(filt)
            .tab_header(
                title="MLB Pitcher Win-Loss Records: Skill or Luck?",
                subtitle="Win-loss records are often as influenced by 'luck' (run support and team errors) as by pitcher skill (ERA).",
            )
            .tab_source_note(html(source_note_md))
            .cols_hide(
                [
                    "Games Started",
                    "Wins",
                    "Losses",
                    "Team",
                    "Team Runs",
                    "Starting Pitcher ID",
                ]
            )
            .cols_move_to_start(
                [
                    "Logo",
                    "headshot_img",
                    "Starting Pitcher",
                    "ERA",
                    "Record",
                ]
            )
            .cols_label(
                {
                    "Starting Pitcher": "Pitcher",
                    "headshot_img": "",
                    "WinLoss": "Games Started",
                    "Logo": "",
                    "Team Errors": "Luck",
                }
            )
            .fmt_image("Logo")
            .fmt_image("headshot_img")
            .cols_align(
                "center",
                ["ERA", "Record", "Team Errors", "WinLoss"],
            )
            .pipe(
                gte.gt_plt_winloss,
                "WinLoss",
                width=250,
                spacing=1.5,
                loss_color="darkorange",
            )
            .pipe(gte.gt_theme_538)
            .pipe(gt_plt_split_bar, columns=("Team Errors", "Team Runs"), width=225)
            .pipe(
                gte.gt_color_box,
                columns="ERA",
                palette=["Green", "Grey", "Red"],
                domain=[1.5, 7.5],
            )
        )
        return ui.HTML(gt.as_raw_html())


MLB_TEAM_ABBREVIATIONS = {
    "NYA": "NYY",
    "NYN": "NYM",
    "SFN": "SF",
    "SDN": "SD",
    "TBA": "TB",
    "KCA": "KC",
    "CHA": "CWS",
    "CHN": "CHC",
    "ANA": "LAA",
    "LAN": "LAD",
    "SLN": "STL",
}
