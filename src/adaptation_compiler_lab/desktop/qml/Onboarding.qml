import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 760
    height: 600
    minimumWidth: 680
    minimumHeight: 540
    visible: true
    title: "Set up Adaptation Compiler"

    FileDialog {
        id: configDialog
        title: "Choose your governed runtime config"
        nameFilters: ["JSON files (*.json)"]
        onAccepted: setupController.inspectConfig(selectedFile.toString())
    }

    FileDialog {
        id: predecessorDialog
        title: "Choose the preserved predecessor config"
        nameFilters: ["JSON files (*.json)"]
        onAccepted: setupController.inspectPredecessor(selectedFile.toString())
    }

    Rectangle {
        anchors.fill: parent
        color: palette.window

        ColumnLayout {
            anchors.centerIn: parent
            width: Math.min(parent.width - 96, 620)
            spacing: 20

            Rectangle {
                width: 56
                height: 56
                radius: 16
                color: "#4d6bfe"
            }
            Label {
                text: "Your behavior layer, under your control"
                font.pixelSize: 29
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                text: "Adaptation Compiler turns approved feedback into scoped, reversible guidance for fresh AI sessions. Raw evidence stays encrypted on this device."
                color: palette.windowText
                opacity: 0.72
                font.pixelSize: 16
                lineHeight: 1.25
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            Frame {
                Layout.fillWidth: true
                padding: 20
                ColumnLayout {
                    width: parent.width
                    spacing: 12
                    Label {
                        text: "Private alpha setup"
                        font.pixelSize: 18
                        font.weight: Font.DemiBold
                    }
                    Label {
                        text: "This build safely imports an existing governed local setup. One-click enrollment for a new tester is intentionally not enabled yet."
                        opacity: 0.7
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Button {
                        text: "Choose current setup"
                        onClicked: configDialog.open()
                    }
                    Label {
                        visible: setupController.selectedPath.length > 0
                        text: setupController.selectedPath
                        opacity: 0.65
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                    Button {
                        text: "Add preserved predecessor (if required)"
                        flat: true
                        onClicked: predecessorDialog.open()
                    }
                    Label {
                        visible: setupController.predecessorPath.length > 0
                        text: setupController.predecessorPath
                        opacity: 0.65
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                    Label {
                        visible: setupController.message.length > 0
                        text: setupController.message
                        color: setupController.messageIsError ? "#d64a4a" : "#3a8c5a"
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Button {
                    text: "Save and close"
                    highlighted: true
                    enabled: setupController.canContinue
                    onClicked: setupController.continueWithConfig()
                }
            }
            Label {
                text: "Reopen Adaptation Compiler after setup. Background observation and aggregate reporting remain off until you enable each one separately."
                opacity: 0.62
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }
}
