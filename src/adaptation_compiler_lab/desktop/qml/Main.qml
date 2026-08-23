import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1180
    height: 760
    minimumWidth: 900
    minimumHeight: 620
    visible: true
    title: "Adaptation Compiler"
    color: palette.window

    property int currentPage: 0
    property bool advancedMode: false
    property color accent: "#4d6bfe"
    property color softAccent: palette.window.hslLightness < 0.5 ? "#20294a" : "#eef1ff"
    property color cardColor: palette.window.hslLightness < 0.5 ? "#202124" : "#ffffff"
    property color mutedText: palette.windowText.hslLightness > 0.5 ? "#aeb3bf" : "#5e6472"

    component Surface: Rectangle {
        radius: 16
        color: root.cardColor
        border.color: palette.window.hslLightness < 0.5 ? "#303238" : "#e6e8ef"
        border.width: 1
    }

    component NavButton: Button {
        required property int page
        required property string label
        Layout.fillWidth: true
        flat: true
        checkable: true
        checked: root.currentPage === page
        text: label
        onClicked: root.currentPage = page
        background: Rectangle {
            radius: 10
            color: parent.checked ? root.softAccent : "transparent"
        }
        contentItem: Label {
            text: parent.text
            color: parent.checked ? root.accent : palette.windowText
            font.weight: parent.checked ? Font.DemiBold : Font.Normal
            leftPadding: 14
            verticalAlignment: Text.AlignVCenter
        }
    }

    header: ToolBar {
        height: 58
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 22
            anchors.rightMargin: 22
            Label {
                text: "Adaptation Compiler"
                font.pixelSize: 18
                font.weight: Font.DemiBold
            }
            Item { Layout.fillWidth: true }
            Label {
                text: desktopController.busy ? "Working…" : "Local & governed"
                color: root.mutedText
            }
            BusyIndicator {
                running: desktopController.busy
                visible: running
                implicitWidth: 30
                implicitHeight: 30
            }
            Button {
                text: "Refresh"
                enabled: !desktopController.busy
                onClicked: desktopController.refresh()
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Pane {
            Layout.preferredWidth: 218
            Layout.fillHeight: true
            padding: 16
            background: Rectangle {
                color: palette.window.hslLightness < 0.5 ? "#18191c" : "#f7f8fb"
                border.color: palette.window.hslLightness < 0.5 ? "#303238" : "#e4e6ec"
            }
            ColumnLayout {
                anchors.fill: parent
                spacing: 6
                Label {
                    text: "YOUR LAYER"
                    color: root.mutedText
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    leftPadding: 14
                    bottomPadding: 8
                }
                NavButton { page: 0; label: "Home" }
                NavButton { page: 1; label: "Suggestions  " + desktopController.suggestionCount }
                NavButton { page: 2; label: "Adaptations  " + desktopController.adaptationCount }
                NavButton { page: 3; label: "Run a task" }
                NavButton { page: 4; label: "Activity  " + desktopController.feedbackCount }
                Item { Layout.fillHeight: true }
                Switch {
                    text: "Advanced"
                    checked: root.advancedMode
                    onToggled: root.advancedMode = checked
                }
                NavButton { page: 5; label: "Settings" }
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.currentPage

            ScrollView {
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width
                    spacing: 18
                    anchors.margins: 28
                    Label {
                        text: "Good " + (new Date().getHours() < 12 ? "morning" : new Date().getHours() < 18 ? "afternoon" : "evening")
                        font.pixelSize: 28
                        font.weight: Font.DemiBold
                    }
                    Label { text: "Here’s what your behavior layer needs today."; color: root.mutedText }
                    Surface {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 150
                        color: root.softAccent
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 24
                            spacing: 20
                            Rectangle { width: 48; height: 48; radius: 24; color: root.accent }
                            ColumnLayout {
                                Layout.fillWidth: true
                                Label { text: desktopController.statusTitle; font.pixelSize: 21; font.weight: Font.DemiBold }
                                Label { text: desktopController.statusDetail; color: root.mutedText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            }
                            Button {
                                text: desktopController.suggestionCount > 0 ? "Review" : "Check now"
                                onClicked: desktopController.suggestionCount > 0 ? root.currentPage = 1 : desktopController.poll()
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 14
                        Repeater {
                            model: [
                                {label: "Suggestions", value: desktopController.suggestionCount},
                                {label: "Active adaptations", value: desktopController.adaptationCount},
                                {label: "Feedback waiting", value: desktopController.feedbackCount}
                            ]
                            Surface {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: 112
                                ColumnLayout {
                                    anchors.fill: parent; anchors.margins: 20
                                    Label { text: modelData.value; font.pixelSize: 30; font.weight: Font.DemiBold }
                                    Label { text: modelData.label; color: root.mutedText }
                                }
                            }
                        }
                    }
                    Label {
                        visible: root.advancedMode
                        text: "Consent: " + desktopController.consentDaysRemaining + " days remaining · Background: " + (desktopController.backgroundEnabled ? "on" : "off")
                        color: root.mutedText
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            ScrollView {
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width; spacing: 16; anchors.margins: 28
                    Label { text: "Suggestions"; font.pixelSize: 28; font.weight: Font.DemiBold }
                    Label { text: "Nothing influences future sessions until you approve it."; color: root.mutedText }
                    Label {
                        visible: desktopController.suggestions.length === 0
                        text: "No suggestions are waiting. Keep working normally."
                        color: root.mutedText
                    }
                    Repeater {
                        model: desktopController.suggestions
                        Surface {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.preferredHeight: detailColumn.implicitHeight + 42
                            ColumnLayout {
                                id: detailColumn
                                anchors.fill: parent; anchors.margins: 20; spacing: 10
                                Label { text: modelData.behavior; font.pixelSize: 18; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                Label { text: modelData.scope; color: root.mutedText }
                                Label { text: modelData.why; color: root.mutedText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                Label { visible: root.advancedMode; text: "Route: " + modelData.route + " · Queue: " + modelData.queueId + "\nDigest: " + modelData.digest; color: root.mutedText; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                                RowLayout {
                                    Button { text: "Approve for future work"; onClicked: desktopController.approve(modelData.queueId, modelData.digest) }
                                    Button { text: "Not a preference"; flat: true; onClicked: desktopController.reject(modelData.queueId, modelData.digest) }
                                }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            ScrollView {
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width; spacing: 16; anchors.margins: 28
                    Label { text: "Adaptations"; font.pixelSize: 28; font.weight: Font.DemiBold }
                    Label { text: "The behaviors currently available to relevant sessions."; color: root.mutedText }
                    Label { visible: desktopController.adaptations.length === 0; text: "No adaptations are active right now."; color: root.mutedText }
                    Repeater {
                        model: desktopController.adaptations
                        Surface {
                            required property var modelData
                            Layout.fillWidth: true; Layout.preferredHeight: adaptationColumn.implicitHeight + 42
                            ColumnLayout {
                                id: adaptationColumn
                                anchors.fill: parent; anchors.margins: 20; spacing: 9
                                Label { text: modelData.intent; font.pixelSize: 18; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                Label { text: modelData.behavior; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                Label { text: modelData.scope; color: root.mutedText }
                                Label { visible: root.advancedMode; text: modelData.type + " · " + modelData.evidenceCount + " supporting evidence · " + modelData.id; color: root.mutedText; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                                Button { text: "Undo adaptation"; flat: true; onClicked: desktopController.revoke(modelData.id) }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            ScrollView {
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width; spacing: 16; anchors.margins: 28
                    Label { text: "Run with Adaptation Compiler"; font.pixelSize: 28; font.weight: Font.DemiBold }
                    Label { text: "One fresh Codex task with only the relevant compact projection."; color: root.mutedText }
                    Surface {
                        Layout.fillWidth: true; Layout.preferredHeight: runnerColumn.implicitHeight + 48
                        ColumnLayout {
                            id: runnerColumn
                            anchors.fill: parent; anchors.margins: 22; spacing: 12
                            ComboBox { id: projectPicker; Layout.fillWidth: true; model: desktopController.projects; textRole: "name" }
                            TextArea { id: taskInput; Layout.fillWidth: true; Layout.preferredHeight: 130; placeholderText: "What should Codex do?"; wrapMode: TextEdit.Wrap }
                            Label { text: "Fresh session · saved ChatGPT login · scoped adaptation · network denied"; color: root.mutedText }
                            Button {
                                text: desktopController.busy ? "Running…" : "Start governed task"
                                enabled: !desktopController.busy && projectPicker.currentIndex >= 0 && projectPicker.currentValue.taskRunnerEnabled && taskInput.text.trim().length > 0
                                onClicked: desktopController.runTask(taskInput.text, projectPicker.currentValue.id)
                            }
                            Label { visible: desktopController.taskResult.length > 0; text: desktopController.taskResult; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            ColumnLayout {
                                visible: desktopController.changeReview.sessionId !== undefined
                                Layout.fillWidth: true
                                spacing: 10
                                Label {
                                    text: "Review before applying"
                                    font.pixelSize: 18
                                    font.weight: Font.DemiBold
                                }
                                Label {
                                    text: (desktopController.changeReview.changedFiles || []).length + " changed file(s). Nothing has touched your project yet."
                                    color: root.mutedText
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                                ScrollView {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 260
                                    TextArea {
                                        readOnly: true
                                        text: desktopController.changeReview.diff || ""
                                        font.family: "monospace"
                                        wrapMode: TextEdit.NoWrap
                                        selectByMouse: true
                                    }
                                }
                                Label {
                                    visible: (desktopController.changeReview.binaryCount || 0) > 0
                                    text: desktopController.changeReview.binaryCount + " binary change(s) cannot be previewed as text."
                                    color: "#c27827"
                                }
                                Label {
                                    text: "Apply succeeds only if the project is still at the reviewed commit and independent checks pass; otherwise it rolls back."
                                    color: root.mutedText
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                                RowLayout {
                                    Button {
                                        text: "Apply reviewed changes"
                                        enabled: !desktopController.busy
                                        onClicked: desktopController.applyChanges(
                                            desktopController.changeReview.sessionId,
                                            desktopController.changeReview.expectedHead
                                        )
                                    }
                                    Button {
                                        text: "Discard"
                                        flat: true
                                        enabled: !desktopController.busy
                                        onClicked: desktopController.discardChanges(desktopController.changeReview.sessionId)
                                    }
                                }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            ScrollView {
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width; spacing: 16; anchors.margins: 28
                    Label { text: "Activity"; font.pixelSize: 28; font.weight: Font.DemiBold }
                    Label { text: "Tell Adaptation Compiler whether a recent activation was useful."; color: root.mutedText }
                    Label { visible: desktopController.pendingFeedback.length === 0; text: "No completed tasks need feedback."; color: root.mutedText }
                    Repeater {
                        model: desktopController.pendingFeedback
                        Surface {
                            required property var modelData
                            Layout.fillWidth: true; Layout.preferredHeight: 150
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 20
                                Label { text: "Recent governed task"; font.pixelSize: 17; font.weight: Font.DemiBold }
                                Label { text: modelData.artifactCount + " adaptations · " + modelData.projectionBytes + " bytes"; color: root.mutedText }
                                RowLayout {
                                    Button { text: "Helped"; onClicked: desktopController.recordFeedback(modelData.activationId, "helped") }
                                    Button { text: "Hurt"; onClicked: desktopController.recordFeedback(modelData.activationId, "hurt") }
                                    Button { text: "Irrelevant"; flat: true; onClicked: desktopController.recordFeedback(modelData.activationId, "irrelevant") }
                                }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            ScrollView {
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width; spacing: 16; anchors.margins: 28
                    Label { text: "Settings"; font.pixelSize: 28; font.weight: Font.DemiBold }
                    Surface {
                        Layout.fillWidth: true; Layout.preferredHeight: settingsColumn.implicitHeight + 44
                        ColumnLayout {
                            id: settingsColumn
                            anchors.fill: parent; anchors.margins: 20; spacing: 12
                            Label { text: "Privacy and control"; font.pixelSize: 18; font.weight: Font.DemiBold }
                            Label { text: "Consent expires in " + desktopController.consentDaysRemaining + " days" }
                            Button {
                                text: "Renew for 30 days"
                                visible: desktopController.consentDaysRemaining <= 7
                                onClicked: desktopController.renewConsent()
                            }
                            Switch {
                                text: "Background learning"
                                checked: desktopController.backgroundEnabled
                                onClicked: desktopController.setBackgroundEnabled(checked)
                            }
                            Label { text: "Starts after sign-in and surfaces suggestions for review."; color: root.mutedText }
                            Switch {
                                text: "Allow sanitized aggregate report previews"
                                checked: desktopController.reportingEnabled
                                onClicked: desktopController.setReportingEnabled(checked)
                            }
                            Label { text: "Unchecked by default. Uploads stay disabled until invite enrollment is connected and you explicitly approve a preview."; color: root.mutedText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            Label { text: "Raw evidence stays encrypted on this device and is never included in aggregate reports."; color: root.mutedText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }
        }
    }

    footer: ToolBar {
        visible: desktopController.message.length > 0
        height: visible ? 48 : 0
        Label {
            anchors.centerIn: parent
            text: desktopController.message
            color: desktopController.messageIsError ? "#d64a4a" : palette.windowText
        }
    }
}
