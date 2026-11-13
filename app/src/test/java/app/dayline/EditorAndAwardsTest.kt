package app.dayline

import androidx.compose.ui.graphics.Color
import org.junit.Assert.*
import org.junit.Test

class EditorAndAwardsTest {
    @Test fun enterContinuesChecklistWithUncheckedItemAndMatchingIndent() {
        val b = Block("item", "check", "Хлеб", checked = true, bold = true, indent = 1)
        val after = Block("after", text = "Дальше")
        val edit = splitListOnEnter(listOf(b, after), b.id, "Хлеб\n", 5)!!
        assertEquals(3, edit.blocks.size)
        assertEquals("item", edit.blocks[0].id)
        assertEquals("Хлеб", edit.blocks[0].text)
        assertTrue(edit.blocks[0].checked)
        val next = edit.blocks[1]
        assertEquals("check", next.kind)
        assertEquals("", next.text)
        assertFalse(next.checked)
        assertTrue(next.bold)
        assertEquals(1, next.indent)
        assertEquals(next.id, edit.focusId)
        assertEquals(0, edit.cursor)
        assertEquals(after, edit.blocks[2])
    }
    @Test fun enterAtCursorSplitsTextRatherThanAppendingAtEnd() {
        val b = Block("item", "bullet", "Купить хлеб")
        val edit = splitListOnEnter(listOf(b), b.id, "Купить\n хлеб", 7)!!
        assertEquals(listOf("Купить", " хлеб"), edit.blocks.map { it.text })
        assertEquals(edit.blocks[1].id, edit.focusId)
        assertEquals(0, edit.cursor)
    }
    @Test fun enterOnEmptyNestedItemExitsList() {
        val b = Block("item", "check", indent = 2)
        val edit = splitListOnEnter(listOf(b), b.id, "\n", 1)!!
        assertEquals(1, edit.blocks.size)
        assertEquals("text", edit.blocks.single().kind)
        assertEquals(0, edit.blocks.single().indent)
        assertEquals("", edit.blocks.single().text)
        assertEquals(b.id, edit.focusId)
    }
    @Test fun multilinePasteCreatesIndependentListItemsAndPreservesCaret() {
        val b = Block("item", "bullet")
        val text = "Один\nДва\nТри"
        val edit = splitListOnEnter(listOf(b), b.id, text, text.length)!!
        assertEquals(listOf("Один", "Два", "Три"), edit.blocks.map { it.text })
        assertEquals(3, edit.blocks.map { it.id }.distinct().size)
        assertEquals(edit.blocks.last().id, edit.focusId)
        assertEquals(3, edit.cursor)
    }
    @Test fun oldMultilineListTextIsNotSplitByAnOrdinaryCharacterEdit() {
        val b = Block("item", "check", "Первая\nВторая")
        assertNull(splitListOnEnter(listOf(b), b.id, "Первая\nВторая!", 15))
    }
    @Test fun paragraphsKeepNormalLineBreaks() {
        val b = Block("item", "text", "Лекция")
        assertNull(splitListOnEnter(listOf(b), b.id, "Лекция\nДЗ", 9))
    }
    @Test fun oldHabitProgressMigratesToDatedMedals() {
        val dates = (1..7).map { "2026-11-%02d".format(it) }.toSet()
        val h = Habit("habit", "Чтение", completed = dates)
        val old = StateCodec.encode(DayState(habits = listOf(h)))
        val migrated = StateCodec.decode(old)
        assertEquals(listOf(1, 7), migrated.awards.map { it.target })
        assertEquals(listOf("2026-11-01", "2026-11-07"), migrated.awards.map { it.earnedOn })
        assertEquals(migrated, StateCodec.decode(StateCodec.encode(migrated)))
    }
    @Test fun awardedMedalSurvivesRemovingHabitAndUndoingCompletion() {
        val h = Habit("habit", "Спорт", completed = setOf("2026-11-13"))
        val awarded = rememberAwards(DayState(habits = listOf(h)))
        val undone = rememberAwards(awarded.copy(habits = listOf(h.copy(completed = emptySet()))))
        assertEquals(awarded.awards, undone.awards)
        val removed = StateCodec.decode(StateCodec.encode(awarded.copy(habits = emptyList())))
        assertEquals(awarded.awards, removed.awards)
    }
    @Test fun migrationAndRepeatCompletionCannotDuplicateMedals() {
        val h = Habit("habit", "Читать", completed = setOf("2026-11-13"))
        val s = rememberAwards(DayState(habits = listOf(h)))
        assertEquals(s, rememberAwards(rememberAwards(s)))
        assertEquals(1, s.awards.size)
    }
    @Test fun screenshotPaletteGetsReadableForegroundOnYellowAndDarkSurfaces() {
        val yellow = Color(0xFFEBA50D)
        val faint = Color(0xFFC7A68B)
        assertTrue(textContrast(faint, yellow) < 4.5f)
        val chosen = legibleText(yellow, faint)
        assertTrue(textContrast(chosen, yellow) >= 4.5f)
        val dark = Color(0xFF210D02)
        assertTrue(textContrast(legibleText(dark, Color(0xFF463022)), dark) >= 4.5f)
    }
    @Test fun alreadyReadableThemeTextIsPreserved() {
        val background = Color(0xFF210D02)
        val foreground = Color(0xFFFFE0CC)
        assertEquals(foreground, legibleText(background, foreground))
    }
}
