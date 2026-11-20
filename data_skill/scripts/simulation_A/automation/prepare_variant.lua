-- Apply one variant's CAD parameters, generate the 1 GHz simulation mesh,
-- export that exact mesh as CFM, and convert the same CFM to NASTRAN.

assert(VARIANT_CONFIG_PATH, [[VARIANT_CONFIG_PATH was not supplied]])
local config = dofile(VARIANT_CONFIG_PATH)
local application = cf.Application.GetInstance()
local project = application:Load({config.source_cfx})

application:SaveAs(config.model_name .. [[.cfx]])
project = application.Project

local variables = project.Definitions.Variables
for name, _ in pairs(config.parameters) do
    assert(variables:Contains(name), [[Missing CADFEKO variable: ]] .. name)
end
variables:SetExpressions(config.parameters)

print([[Model: ]] .. config.model_name)
print([[Model unit: ]] .. tostring(project.ModelAttributes.Unit))
for name, _ in pairs(config.parameters) do
    print(name .. [[ = ]] .. tostring(variables:Item(name).EvaluatedValue))
end

local frequency = project.Contents.SolutionConfigurations.GlobalFrequency
local frequency_properties = frequency:GetProperties()
frequency_properties.RangeType = cf.Enums.FrequencyRangeTypeEnum.Single
frequency_properties.Start = config.frequency_hz
frequency:SetProperties(frequency_properties)

project.Mesher.Settings.MeshSizeOption = cf.Enums.MeshSizeOptionEnum.Standard
print([[Generating Standard automatic simulation mesh at 1 GHz...]])
project.Mesher:Mesh()
application:Save()

local output_cfm = config.model_name .. [[.cfm]]
local output_nas = config.model_name .. [[.nas]]
local mesh_exporter = project.Exporter.Mesh
mesh_exporter.ExportMeshType = cf.Enums.ExportMeshTypeEnum.SimulationMesh
mesh_exporter.ScaleToMetreEnabled = true
mesh_exporter.ExportFileFormat = cf.Enums.ExportMeshFileFormatEnum.CADFEKOMesh
mesh_exporter:Export(output_cfm)

local mesh_project = application:NewProject()
local mesh_importer = mesh_project.Importer.MeshImporter
mesh_importer.GroupPartsByLabelEnabled = true
mesh_importer.TriangleImportingEnabled = true
mesh_importer.TetrahedronImportingEnabled = false
mesh_importer:Import(output_cfm)

local nas_exporter = mesh_project.Exporter.Mesh
nas_exporter.ExportMeshType = cf.Enums.ExportMeshTypeEnum.ModelMesh
nas_exporter.ExportFileFormat = cf.Enums.ExportMeshFileFormatEnum.NASTRAN
nas_exporter.ScaleToMetreEnabled = true
nas_exporter:Export(output_nas)

print([[Saved parameterised CFX: ]] .. config.model_name .. [[.cfx]])
print([[Exported SimulationMesh CFM: ]] .. output_cfm)
print([[Converted solver CFM to NAS: ]] .. output_nas)
application:Exit()
